"""Combined scoring.

Combination policy, stated explicitly because it is a risk decision and not
a modelling one:

    final = max(rule_score, model_score * MODEL_TRUST)

A rule hit alone is sufficient to alert -- the model can never veto a rule.
The model can only *raise* a score, never lower it. MODEL_TRUST caps how
loud an unexplained statistical signal is allowed to be relative to a
written, reviewable rule.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from .model import ModelBundle
from .rules import RuleContext, RuleHit, evaluate, rule_score

MODEL_TRUST = 0.75
ALERT_THRESHOLD = 0.45


@dataclass
class Score:
    txn_id: str
    final_score: float
    rule_score: float
    model_score: float
    alerts: bool
    hits: list[RuleHit] = field(default_factory=list)
    attribution: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "txn_id": self.txn_id,
            "final_score": round(self.final_score, 4),
            "rule_score": round(self.rule_score, 4),
            "model_score": round(self.model_score, 4),
            "alerts": self.alerts,
            "hits": [asdict(h) for h in self.hits],
            "attribution": self.attribution,
            "threshold": ALERT_THRESHOLD,
        }


def evidence_ids(score: Score) -> set[str]:
    """Every ID the summarizer is permitted to cite for this score."""
    ids = {score.txn_id}
    for hit in score.hits:
        ids.update(hit.evidence_txn_ids)
        ids.add(hit.rule_id)
    return ids


class Scorer:
    def __init__(self, bundle: ModelBundle, corridors: pd.DataFrame,
                 institutions: dict, ledger) -> None:
        self.bundle = bundle
        self.corridors = corridors
        self.institutions = institutions
        self.ledger = ledger
        self._cstats = {
            (r.sender_bic, r.receiver_bic): r._asdict()
            for r in corridors.itertuples(index=False)
        }

    def score_one(self, txn: dict) -> Score:
        history = self.ledger.corridor_history(
            txn["sender_bic"], txn["receiver_bic"], before=txn["booked_at"]
        )
        ctx = RuleContext(
            txn=txn,
            history=history,
            corridor_stats=self._cstats.get((txn["sender_bic"], txn["receiver_bic"])),
            institutions=self.institutions,
        )
        hits = evaluate(ctx)
        rs = rule_score(hits)

        from .features import build_features

        X = build_features(pd.DataFrame([txn]), self.corridors, self.institutions)
        ms = float(self.bundle.score(X)[0])
        attribution = self.bundle.attribute(X, 0)

        final = max(rs, ms * MODEL_TRUST)
        return Score(
            txn_id=txn["txn_id"],
            final_score=final,
            rule_score=rs,
            model_score=ms,
            alerts=final >= ALERT_THRESHOLD,
            hits=hits,
            attribution=attribution,
        )

    def score_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorised model scoring + per-row rules. Used by evals."""
        from .features import build_features

        X = build_features(df, self.corridors, self.institutions)
        model_scores = self.bundle.score(X)

        rule_scores, all_hits = [], []
        for txn in df.to_dict("records"):
            history = self.ledger.corridor_history(
                txn["sender_bic"], txn["receiver_bic"], before=txn["booked_at"]
            )
            ctx = RuleContext(
                txn=txn,
                history=history,
                corridor_stats=self._cstats.get((txn["sender_bic"], txn["receiver_bic"])),
                institutions=self.institutions,
            )
            hits = evaluate(ctx)
            rule_scores.append(rule_score(hits))
            all_hits.append([h.rule_id for h in hits])

        out = df[["txn_id"]].copy()
        out["rule_score"] = rule_scores
        out["model_score"] = model_scores
        out["final_score"] = [
            max(r, m * MODEL_TRUST) for r, m in zip(rule_scores, model_scores)
        ]
        out["alerts"] = out["final_score"] >= ALERT_THRESHOLD
        out["rule_ids"] = all_hits
        return out