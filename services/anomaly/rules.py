"""Deterministic rules engine.

Design stance: rules are the floor, not the ceiling. They exist so that
(a) a compliance officer can read why an item alerted, and (b) detection
does not silently degrade when the model drifts.

Each rule returns a RuleHit or None. A hit carries the evidence IDs that
justify it -- those IDs are what the summarizer is allowed to cite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Iterable

import pandas as pd

STRUCTURING_THRESHOLD = 10_000.0
DUPLICATE_WINDOW_HOURS = 48
VELOCITY_MULTIPLIER = 3.0


@dataclass
class RuleHit:
    rule_id: str
    severity: str            # "low" | "medium" | "high"
    reason: str
    evidence_txn_ids: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)


@dataclass
class RuleContext:
    """Everything a rule is allowed to look at."""

    txn: dict
    history: pd.DataFrame        # prior transactions, same corridor
    corridor_stats: dict | None
    institutions: dict


def _ref_distance(a: str, b: str) -> int:
    if len(a) != len(b):
        return 99
    return sum(1 for x, y in zip(a, b) if x != y)


def rule_duplicate_settlement(ctx: RuleContext) -> RuleHit | None:
    """Same corridor + same amount + near-identical reference inside 48h."""
    if ctx.history.empty:
        return None
    now = datetime.fromisoformat(ctx.txn["booked_at"])
    window = ctx.history[
        pd.to_datetime(ctx.history["booked_at"], format="ISO8601") >= (now - timedelta(hours=DUPLICATE_WINDOW_HOURS))
    ]
    for _, prior in window.iterrows():
        if abs(prior["amount"] - ctx.txn["amount"]) < 0.01:
            dist = _ref_distance(str(prior["reference"]), str(ctx.txn["reference"]))
            if dist <= 2:
                return RuleHit(
                    "R001_DUPLICATE_SETTLEMENT",
                    "high",
                    f"Amount matches prior settlement {prior['reference']} within "
                    f"{DUPLICATE_WINDOW_HOURS}h; reference differs by {dist} character(s).",
                    [str(prior["txn_id"])],
                    {"prior_reference": prior["reference"], "ref_distance": dist},
                )
    return None


def rule_novel_corridor(ctx: RuleContext) -> RuleHit | None:
    """No prior settlement between this institution pair."""
    if ctx.corridor_stats is None or ctx.history.empty:
        return RuleHit(
            "R002_NOVEL_CORRIDOR",
            "high",
            f"First observed settlement from {ctx.txn['sender_bic']} to "
            f"{ctx.txn['receiver_bic']}. No corridor baseline exists.",
            [],
            {"sender": ctx.txn["sender_bic"], "receiver": ctx.txn["receiver_bic"]},
        )
    return None


def rule_velocity(ctx: RuleContext) -> RuleHit | None:
    """Corridor volume in the last 24h exceeds its trailing-30d daily mean."""
    if ctx.history.empty:
        return None
    now = datetime.fromisoformat(ctx.txn["booked_at"])
    hist_ts = pd.to_datetime(ctx.history["booked_at"], format="ISO8601")
    last_24h = int((hist_ts >= now - timedelta(hours=24)).sum())
    trailing = ctx.history[hist_ts >= now - timedelta(days=30)]
    if len(trailing) < 10:
        return None
    daily_mean = len(trailing) / 30.0
    if daily_mean > 0 and last_24h > VELOCITY_MULTIPLIER * daily_mean:
        return RuleHit(
            "R003_VELOCITY",
            "medium",
            f"{last_24h} settlements in 24h against a trailing 30-day mean of "
            f"{daily_mean:.1f}/day ({last_24h / daily_mean:.1f}x).",
            [str(t) for t in trailing["txn_id"].head(5)],
            {"last_24h": last_24h, "daily_mean": round(daily_mean, 2)},
        )
    return None


def rule_round_amount(ctx: RuleContext) -> RuleHit | None:
    """Amount is suspiciously round for a real settlement."""
    amt = float(ctx.txn["amount"])
    if amt >= 100_000 and amt % 100_000 == 0:
        return RuleHit(
            "R004_ROUND_AMOUNT",
            "low",
            f"Amount {amt:,.2f} is an exact multiple of 100,000 -- unusual for a "
            f"settlement derived from underlying trades.",
            [],
            {"amount": amt},
        )
    return None


def rule_off_window(ctx: RuleContext) -> RuleHit | None:
    """Booked outside the sending institution's local operating window."""
    inst = ctx.institutions.get(ctx.txn["sender_bic"])
    if inst is None:
        return None
    local = (datetime.fromisoformat(ctx.txn["booked_at"]).hour + inst.tz_offset) % 24
    if inst.open_hour <= local <= inst.close_hour:
        return None
    return RuleHit(
        "R005_OFF_WINDOW",
        "medium",
        f"Booked at {local:02d}:00 local, outside {inst.name}'s operating window "
        f"({inst.open_hour:02d}:00-{inst.close_hour:02d}:00).",
        [],
        {"local_hour": local, "window": [inst.open_hour, inst.close_hour]},
    )


def rule_structuring(ctx: RuleContext) -> RuleHit | None:
    """Burst of sub-threshold transactions in a short window."""
    amt = float(ctx.txn["amount_usd"])
    if not (0.75 * STRUCTURING_THRESHOLD <= amt < STRUCTURING_THRESHOLD):
        return None
    if ctx.history.empty:
        return None
    now = datetime.fromisoformat(ctx.txn["booked_at"])
    hist_ts = pd.to_datetime(ctx.history["booked_at"], format="ISO8601")
    recent = ctx.history[
        (hist_ts >= now - timedelta(hours=24))
        & (ctx.history["amount_usd"] >= 0.75 * STRUCTURING_THRESHOLD)
        & (ctx.history["amount_usd"] < STRUCTURING_THRESHOLD)
    ]
    if len(recent) >= 3:
        return RuleHit(
            "R006_STRUCTURING",
            "high",
            f"{len(recent) + 1} settlements in 24h all between "
            f"{0.75 * STRUCTURING_THRESHOLD:,.0f} and {STRUCTURING_THRESHOLD:,.0f} USD "
            f"-- consistent with threshold avoidance.",
            [str(t) for t in recent["txn_id"].head(8)],
            {"burst_size": len(recent) + 1, "threshold": STRUCTURING_THRESHOLD},
        )
    return None


RULES: list[Callable[[RuleContext], RuleHit | None]] = [
    rule_duplicate_settlement,
    rule_novel_corridor,
    rule_velocity,
    rule_round_amount,
    rule_off_window,
    rule_structuring,
]

SEVERITY_WEIGHT = {"low": 0.15, "medium": 0.45, "high": 0.85}


def evaluate(ctx: RuleContext) -> list[RuleHit]:
    hits = []
    for rule in RULES:
        try:
            hit = rule(ctx)
        except Exception as exc:  # a broken rule must not take down scoring
            hit = RuleHit("R000_RULE_ERROR", "low", f"{rule.__name__} raised: {exc}")
        if hit is not None:
            hits.append(hit)
    return hits


def rule_score(hits: Iterable[RuleHit]) -> float:
    """Max severity weight. Deliberately not additive: three low-severity
    hits should not manufacture a high-severity alert."""
    weights = [SEVERITY_WEIGHT.get(h.severity, 0.0) for h in hits]
    return max(weights) if weights else 0.0