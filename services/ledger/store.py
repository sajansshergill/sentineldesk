"""DuckDB-backed transaction ledger.

Read-heavy, single-node, analytical. DuckDB is the right call at this scale
and I would rather ship an honest embedded store than gesture at a warehouse
I am not actually running.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    txn_id        VARCHAR PRIMARY KEY,
    reference     VARCHAR NOT NULL,
    sender_bic    VARCHAR NOT NULL,
    receiver_bic  VARCHAR NOT NULL,
    currency      VARCHAR NOT NULL,
    amount        DOUBLE  NOT NULL,
    amount_usd    DOUBLE  NOT NULL,
    value_date    VARCHAR NOT NULL,
    booked_at     VARCHAR NOT NULL,
    message_type  VARCHAR NOT NULL,
    is_anomaly    BOOLEAN,
    anomaly_class VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_corridor ON transactions (sender_bic, receiver_bic);
CREATE INDEX IF NOT EXISTS idx_booked   ON transactions (booked_at);
CREATE INDEX IF NOT EXISTS idx_ref      ON transactions (reference);
"""


class Ledger:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.con = duckdb.connect(str(path))
        self.con.execute(SCHEMA)
        self._cache: dict[tuple[str, str], pd.DataFrame] = {}

    # ---------- write ----------

    def load_frame(self, df: pd.DataFrame) -> int:
        self.con.execute("DELETE FROM transactions")
        self.con.register("incoming", df)
        self.con.execute("INSERT INTO transactions SELECT * FROM incoming")
        self.con.unregister("incoming")
        self._cache.clear()
        return self.count()

    def insert(self, txn: dict) -> None:
        cols = ", ".join(txn.keys())
        marks = ", ".join("?" for _ in txn)
        self.con.execute(f"INSERT INTO transactions ({cols}) VALUES ({marks})",
                         list(txn.values()))
        self._cache.pop((txn["sender_bic"], txn["receiver_bic"]), None)

    # ---------- read ----------

    def count(self) -> int:
        return self.con.execute("SELECT count(*) FROM transactions").fetchone()[0]

    def get(self, txn_id: str) -> dict | None:
        row = self.con.execute(
            "SELECT * FROM transactions WHERE txn_id = ?", [txn_id]
        ).fetchdf()
        return None if row.empty else row.iloc[0].to_dict()

    def by_reference(self, reference: str) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM transactions WHERE reference = ?", [reference]
        ).fetchdf()

    def corridor_history(self, sender: str, receiver: str,
                         before: str | None = None) -> pd.DataFrame:
        """Prior transactions on a corridor. Cached per corridor because the
        rules engine hammers this path once per scored item."""
        key = (sender, receiver)
        if key not in self._cache:
            self._cache[key] = self.con.execute(
                "SELECT * FROM transactions WHERE sender_bic = ? AND receiver_bic = ? "
                "ORDER BY booked_at",
                [sender, receiver],
            ).fetchdf()
        df = self._cache[key]
        if before is not None and not df.empty:
            df = df[df["booked_at"] < before]
        return df

    def reconcile(self, reference: str, amount: float, currency: str,
                  tolerance: float = 0.01) -> dict:
        """Match an extracted instruction against the ledger.

        Returns a match verdict plus the candidate rows that justify it.
        This is the function the reconcile agent calls, and the txn_ids it
        returns become citable evidence.
        """
        exact = self.by_reference(reference)
        if not exact.empty:
            row = exact.iloc[0]
            amount_ok = abs(float(row["amount"]) - amount) <= tolerance
            currency_ok = row["currency"] == currency
            if amount_ok and currency_ok:
                return {"status": "matched", "txn_id": row["txn_id"],
                        "candidates": [row["txn_id"]], "discrepancies": []}
            disc = []
            if not amount_ok:
                disc.append({"field": "amount", "ledger": float(row["amount"]),
                             "message": amount})
            if not currency_ok:
                disc.append({"field": "currency", "ledger": row["currency"],
                             "message": currency})
            return {"status": "mismatch", "txn_id": row["txn_id"],
                    "candidates": [row["txn_id"]], "discrepancies": disc}

        near = self.con.execute(
            "SELECT txn_id, reference, amount FROM transactions "
            "WHERE currency = ? AND abs(amount - ?) <= ? LIMIT 5",
            [currency, amount, max(tolerance, amount * 0.0001)],
        ).fetchdf()
        return {
            "status": "unmatched",
            "txn_id": None,
            "candidates": near["txn_id"].tolist(),
            "discrepancies": [{"field": "reference", "ledger": None,
                               "message": reference}],
        }

    def close(self) -> None:
        self.con.close()