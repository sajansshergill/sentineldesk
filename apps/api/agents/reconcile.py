"""Stage 3: reconcile.

Deterministic. No LLM. Matching an extracted reference against a ledger is a
database question, and handing it to a model would be both slower and less
defensible.

Every txn_id this touches is added to evidence_ids -- that is what makes it
legal for the summarizer to cite it later.
"""

from __future__ import annotations

from ..schemas import ReconcileResult
from ._stage import stage


def reconcile(state: dict, ledger) -> dict:
    with stage("reconcile") as rec:
        ext = state.get("extraction")
        if not ext or ext.get("amount") is None or not ext.get("reference"):
            rec["ok"] = False
            rec["error"] = "insufficient_extraction"
            return {
                "stages": [rec],
                "reconcile": None,
                "halted_reason": "Extraction lacked a reference or amount; "
                                 "cannot reconcile without them.",
            }

        result = ledger.reconcile(
            reference=ext["reference"],
            amount=ext["amount"],
            currency=ext["currency"] or "",
        )
        rec["tool_calls"].append({
            "tool": "ledger.reconcile",
            "args": {"reference": ext["reference"], "amount": ext["amount"]},
            "status": result["status"],
        })
        validated = ReconcileResult.model_validate(result)

        evidence = list(validated.candidates)
        if validated.txn_id:
            evidence.append(validated.txn_id)

        rec["status"] = validated.status
        return {
            "stages": [rec],
            "reconcile": validated.model_dump(mode="json"),
            "evidence_ids": evidence,
        }
    return {"stages": [rec], "error": rec.get("error")}