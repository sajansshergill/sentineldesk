"""Feature engineering.

Kept deliberately small and explainable. Every feature here is one a
compliance reviewer can be walked through in a sentence, which matters more
than squeezing out the last point of AUC.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_NAMES = [
    "log_amount_usd",
    "amount_z_in_corridor",
    "hour_sin",
    "hour_cos",
    "is_weekend",
    "corridor_freq",
    "days_since_corridor_last_seen",
    "amount_round_score",
    "hours_outside_window",
]


def _round_score(amount: float) -> float:
    """How suspiciously round is this amount? 0 = not round, 1 = very round."""
    if amount <= 0:
        return 0.0
    for scale, score in ((1_000_000, 1.0), (100_000, 0.8), (10_000, 0.6), (1_000, 0.35)):
        if amount % scale == 0:
            return score
    return 0.0


def build_features(df: pd.DataFrame, corridors: pd.DataFrame,
                   institutions: dict) -> pd.DataFrame:
    """Return a frame of FEATURE_NAMES aligned to df's index."""
    out = pd.DataFrame(index=df.index)
    ts = pd.to_datetime(df["booked_at"], format="ISO8601")

    out["log_amount_usd"] = np.log1p(df["amount_usd"].clip(lower=0))

    key = df["sender_bic"] + "|" + df["receiver_bic"]
    cor = corridors.copy()
    cor["key"] = cor["sender_bic"] + "|" + cor["receiver_bic"]
    stats = cor.set_index("key")

    mean = key.map(stats["mean_amount_usd"]).fillna(df["amount_usd"].mean())
    std = key.map(stats["std_amount_usd"]).fillna(df["amount_usd"].std())
    std = std.replace(0, np.nan).fillna(df["amount_usd"].std() or 1.0)
    out["amount_z_in_corridor"] = ((df["amount_usd"] - mean) / std).clip(-20, 20)

    hour = ts.dt.hour + ts.dt.minute / 60.0
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["is_weekend"] = (ts.dt.weekday >= 5).astype(float)

    total = max(len(df), 1)
    out["corridor_freq"] = key.map(stats["txn_count"]).fillna(0.0) / total

    last_seen = pd.to_datetime(key.map(stats["last_seen"]), errors="coerce")
    delta = (ts - last_seen).dt.total_seconds() / 86400.0
    out["days_since_corridor_last_seen"] = delta.fillna(999.0).clip(-999, 999)

    out["amount_round_score"] = df["amount"].map(_round_score)

    # hours outside the sender's local operating window
    def _outside(row) -> float:
        inst = institutions.get(row["sender_bic"])
        if inst is None:
            return 0.0
        local = (pd.Timestamp(row["booked_at"]).hour + inst.tz_offset) % 24
        if inst.open_hour <= local <= inst.close_hour:
            return 0.0
        return float(min(abs(local - inst.open_hour), abs(local - inst.close_hour)))

    out["hours_outside_window"] = df.apply(_outside, axis=1)

    return out[FEATURE_NAMES].astype(float)