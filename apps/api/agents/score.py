"""Stage 4: score.

Deterministic. Delegates to the anomaly service. Adds every rule_id and
evidence txn_id to the allowlist.
"""

from __future__ import annotations

from ._stage import stage


def score(state: dict, ledger, scorer) -> dict:
    with stage("score", model=scorer.bundle.version) as rec:
        recon = state.get("reconcile")
        ext = state.get("extraction") or {}

        txn = None
        if recon and recon.get("txn_id"):
            txn = ledger.get(recon["txn_id"])

        if txn is None:
            # Unmatched instruction: score the extracted fields as a candidate
            # transaction. This is the interesting case -- an instruction with
            # no ledger counterpart is exactly what surveillance is for.
            if not all(ext.get(k) for k in ("sender_bic", "receiver_bic", "currency")):
                rec["ok"] = False
                rec["error"] = "insufficient_fields_to_score"
                return {"stages": [rec], "score": None,
                        "halted_reason": "Too few fields to score; human review."}
            txn = {
                "txn_id": f"candidate:{state['run_id']}",
                "reference": ext.get("reference") or "",
                "sender_bic": ext["sender_bic"],
                "receiver_bic": ext["receiver_bic"],
                "currency": ext["currency"],
                "amount": ext.get("amount") or 0.0,
                "amount_usd": ext.get("amount") or 0.0,
                "value_date": ext.get("value_date") or "",
                "booked_at": state["email"].get("received_at"),
                "message_type": ext.get("message_type") or "UNKNOWN",
            }
            rec["scored_as"] = "unmatched_candidate"
        else:
            rec["scored_as"] = "ledger_transaction"

        result = scorer.score_one(txn)
        rec["tool_calls"].append({"tool": "anomaly.score_one",
                                  "txn_id": txn["txn_id"]})
        rec["final_score"] = round(result.final_score, 4)

        from services.anomaly.scorer import evidence_ids

        return {
            "stages": [rec],
            "score": result.to_dict(),
            "evidence_ids": sorted(evidence_ids(result)),
        }
    return {"stages": [rec], "error": rec.get("error")}