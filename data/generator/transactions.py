"""Baseline (non-anomalous) transaction generation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import (
    BY_BIC,
    DAYS_OF_HISTORY,
    ESTABLISHED_CORRIDORS,
    INSTITUTIONS,
    N_TRANSACTIONS,
)

FX_TO_USD = {
    "USD": 1.0, "EUR": 1.09, "GBP": 1.27, "JPY": 0.0067,
    "CHF": 1.12, "CAD": 0.74, "AUD": 0.66, "SEK": 0.095,
}


def _reference(rng: np.random.Generator, sender: str) -> str:
    """SWIFT-ish sender reference (field :20:)."""
    body = "".join(rng.choice(list("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"), size=10))
    return f"{sender[:4]}{body}"


def _draw_hour(rng: np.random.Generator, bic: str) -> int:
    """Hour in UTC, drawn inside the institution's local operating window."""
    inst = BY_BIC[bic]
    local_hour = int(rng.integers(inst.open_hour, inst.close_hour))
    return (local_hour - inst.tz_offset) % 24


def generate_baseline(
    rng: np.random.Generator,
    n: int = N_TRANSACTIONS,
    days: int = DAYS_OF_HISTORY,
) -> pd.DataFrame:
    """Generate `n` baseline transactions over `days` of history.

    Volume per corridor is proportional to the sending institution's
    `daily_volume`. Amounts are lognormal around the institution's
    `mean_amount`. Timing respects the operating window.
    """
    corridors = sorted(ESTABLISHED_CORRIDORS)
    weights = np.array([BY_BIC[a].daily_volume for a, _ in corridors], dtype=float)
    weights /= weights.sum()

    picks = rng.choice(len(corridors), size=n, p=weights)
    start = datetime(2025, 7, 1)

    rows = []
    for i, pick in enumerate(picks):
        sender, receiver = corridors[pick]
        inst = BY_BIC[sender]

        day = int(rng.integers(0, days))
        # weekday bias: settlements cluster Mon-Fri
        ts = start + timedelta(days=day)
        if ts.weekday() >= 5 and rng.random() < 0.85:
            ts -= timedelta(days=ts.weekday() - 4)

        hour = _draw_hour(rng, sender)
        ts = ts.replace(hour=hour, minute=int(rng.integers(0, 60)),
                        second=int(rng.integers(0, 60)))

        amount = float(rng.lognormal(np.log(inst.mean_amount), 0.85))
        amount = round(amount, 2)

        rows.append({
            "txn_id": str(uuid.uuid4()),
            "reference": _reference(rng, sender),
            "sender_bic": sender,
            "receiver_bic": receiver,
            "currency": inst.base_currency,
            "amount": amount,
            "amount_usd": round(amount * FX_TO_USD[inst.base_currency], 2),
            "value_date": ts.date().isoformat(),
            "booked_at": ts.isoformat(),
            "message_type": "MT202" if rng.random() < 0.6 else "MT103",
            "is_anomaly": False,
            "anomaly_class": None,
        })

    df = pd.DataFrame(rows)
    return df.sort_values("booked_at").reset_index(drop=True)


def corridor_baselines(df: pd.DataFrame) -> pd.DataFrame:
    """Per-corridor summary stats used by the rules engine and features."""
    base = df[~df["is_anomaly"]] if "is_anomaly" in df.columns else df
    g = base.groupby(["sender_bic", "receiver_bic"])
    out = g.agg(
        txn_count=("txn_id", "count"),
        mean_amount_usd=("amount_usd", "mean"),
        std_amount_usd=("amount_usd", "std"),
        first_seen=("booked_at", "min"),
        last_seen=("booked_at", "max"),
    ).reset_index()
    out["std_amount_usd"] = out["std_amount_usd"].fillna(0.0)
    return out