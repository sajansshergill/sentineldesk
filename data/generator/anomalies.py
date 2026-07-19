"""Anomaly injection.

Each function takes the baseline frame and returns *new* rows to append
(and, where relevant, mutates nothing in place). Labels are written to
`anomaly_class` so evals can score per-class precision/recall.

The point of keeping injection separate from generation: the baseline is
"what normal looks like", and anomalies are perturbations of it. If injection
leaked into the baseline, detection metrics would be measuring the generator.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import BY_BIC, ESTABLISHED_CORRIDORS, STRUCTURING_THRESHOLD
from .transactions import FX_TO_USD, _reference


def _clone(row: pd.Series, **overrides) -> dict:
    d = row.to_dict()
    d["txn_id"] = str(uuid.uuid4())
    d.update(overrides)
    return d


def inject_duplicate_settlement(rng, df: pd.DataFrame, n: int) -> list[dict]:
    """Resend of a settled instruction within 48h, reference mutated by one char.

    Detectable by rules: same corridor + amount + near-identical reference
    inside a short window.
    """
    out = []
    picks = rng.choice(len(df), size=n, replace=False)
    for idx in picks:
        row = df.iloc[idx]
        ref = list(row["reference"])
        pos = int(rng.integers(4, len(ref)))
        ref[pos] = str(rng.choice(list("0123456789")))
        ts = (datetime.fromisoformat(row["booked_at"])
              + timedelta(hours=float(rng.uniform(1, 47)))).replace(microsecond=0)
        out.append(_clone(
            row,
            reference="".join(ref),
            booked_at=ts.isoformat(),
            value_date=ts.date().isoformat(),
            is_anomaly=True,
            anomaly_class="duplicate_settlement",
        ))
    return out


def inject_amount_transposition(rng, df: pd.DataFrame, n: int) -> list[dict]:
    """Two adjacent digits swapped versus the confirmation.

    Detectable by rules (amount mismatch vs. paired confirmation) and by the
    model (resulting amount is an outlier for the corridor).
    """
    out = []
    picks = rng.choice(len(df), size=n, replace=False)
    for idx in picks:
        row = df.iloc[idx]
        whole = str(int(row["amount"]))
        if len(whole) < 3:
            continue
        pos = int(rng.integers(0, len(whole) - 1))
        digits = list(whole)
        if digits[pos] == digits[pos + 1]:
            digits[pos] = str((int(digits[pos]) + 3) % 10)
        digits[pos], digits[pos + 1] = digits[pos + 1], digits[pos]
        new_amount = float("".join(digits))
        out.append(_clone(
            row,
            amount=new_amount,
            amount_usd=round(new_amount * FX_TO_USD[row["currency"]], 2),
            reference=_reference(rng, row["sender_bic"]),
            is_anomaly=True,
            anomaly_class="amount_transposition",
        ))
    return out


def inject_novel_corridor(rng, df: pd.DataFrame, n: int) -> list[dict]:
    """First-ever settlement between an institution pair."""
    bics = list(BY_BIC)
    novel = [
        (a, b) for a in bics for b in bics
        if a != b and (a, b) not in ESTABLISHED_CORRIDORS
    ]
    out = []
    for _ in range(n):
        sender, receiver = novel[int(rng.integers(0, len(novel)))]
        inst = BY_BIC[sender]
        template = df.iloc[int(rng.integers(0, len(df)))]
        amount = round(float(rng.lognormal(np.log(inst.mean_amount), 0.9)), 2)
        out.append(_clone(
            template,
            reference=_reference(rng, sender),
            sender_bic=sender,
            receiver_bic=receiver,
            currency=inst.base_currency,
            amount=amount,
            amount_usd=round(amount * FX_TO_USD[inst.base_currency], 2),
            is_anomaly=True,
            anomaly_class="novel_corridor",
        ))
    return out


def inject_off_cycle_timing(rng, df: pd.DataFrame, n: int) -> list[dict]:
    """Booked outside the sender's local operating window.

    Model-detectable: no single rule fires, but the hour-of-day features are
    far from the corridor's baseline.
    """
    out = []
    picks = rng.choice(len(df), size=n, replace=False)
    for idx in picks:
        row = df.iloc[idx]
        inst = BY_BIC[row["sender_bic"]]
        # pick a local hour well outside [open, close]
        dead_hours = [h for h in range(24) if not (inst.open_hour <= h <= inst.close_hour)]
        local_hour = int(rng.choice(dead_hours))
        utc_hour = (local_hour - inst.tz_offset) % 24
        ts = datetime.fromisoformat(row["booked_at"]).replace(hour=utc_hour)
        out.append(_clone(
            row,
            reference=_reference(rng, row["sender_bic"]),
            booked_at=ts.isoformat(),
            is_anomaly=True,
            anomaly_class="off_cycle_timing",
        ))
    return out


def inject_structuring(rng, df: pd.DataFrame, n_bursts: int) -> list[dict]:
    """Bursts of 4-9 transactions each just under the reporting threshold."""
    out = []
    for _ in range(n_bursts):
        template = df.iloc[int(rng.integers(0, len(df)))]
        base_ts = datetime.fromisoformat(template["booked_at"])
        burst = int(rng.integers(4, 10))
        for k in range(burst):
            amount = round(float(rng.uniform(0.82, 0.985)) * STRUCTURING_THRESHOLD, 2)
            ts = (base_ts + timedelta(minutes=int(rng.integers(3, 90)) * (k + 1))
                  ).replace(microsecond=0)
            out.append(_clone(
                template,
                reference=_reference(rng, template["sender_bic"]),
                currency="USD",
                amount=amount,
                amount_usd=amount,
                booked_at=ts.isoformat(),
                value_date=ts.date().isoformat(),
                is_anomaly=True,
                anomaly_class="structuring",
            ))
    return out


def inject_drift(rng, df: pd.DataFrame, n: int) -> list[dict]:
    """Unlabeled joint drift in amount and timing.

    Deliberately has no matching rule. This is the class that justifies the
    Isolation Forest existing at all -- if the model can't beat the rules
    here, the model is decoration.
    """
    out = []
    picks = rng.choice(len(df), size=n, replace=False)
    for idx in picks:
        row = df.iloc[idx]
        inst = BY_BIC[row["sender_bic"]]
        mult = float(rng.uniform(3.5, 9.0))
        amount = round(row["amount"] * mult, 2)
        ts = datetime.fromisoformat(row["booked_at"])
        shift = int(rng.choice([-4, -3, 3, 4]))
        ts = ts.replace(hour=(ts.hour + shift) % 24)
        out.append(_clone(
            row,
            reference=_reference(rng, row["sender_bic"]),
            amount=amount,
            amount_usd=round(amount * FX_TO_USD[row["currency"]], 2),
            booked_at=ts.isoformat(),
            is_anomaly=True,
            anomaly_class="drift",
        ))
    return out


INJECTORS = {
    "duplicate_settlement": inject_duplicate_settlement,
    "amount_transposition": inject_amount_transposition,
    "novel_corridor": inject_novel_corridor,
    "off_cycle_timing": inject_off_cycle_timing,
    "structuring": inject_structuring,
    "drift": inject_drift,
}