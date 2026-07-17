"""Stage 7: commit.

Runs only after a human decision. Writes to CRM with an idempotency key
derived from the run id, because the one thing worse than not writing to a
system of record is writing to it twice.
"""

from __future__ import annotations

from ._stage import stage


def commit(state: dict, crm) -> dict:
    with stage("commit") as rec:
        decision = state.get("decision")
        if decision == "rejected":
            rec["tool_calls"].append({"tool": "crm.noop", "reason": "rejected"})
            return {"stages": [rec], "committed": {"status": "skipped",
                                                   "reason": "analyst_rejected"}}

        brief = dict(state.get("brief") or {})
        brief.update(state.get("edits") or {})

        result = crm.upsert_case(
            idempotency_key=state["run_id"],
            reference=(state.get("extraction") or {}).get("reference"),
            score=(state.get("score") or {}).get("final_score"),
            headline=brief.get("headline"),
            summary=brief.get("summary"),
            recommended_action=brief.get("recommended_action"),
            actor=state.get("actor"),
            decision=decision,
        )
        rec["tool_calls"].append({"tool": "crm.upsert_case",
                                  "record_id": result.get("record_id")})
        return {"stages": [rec], "committed": result}
    return {"stages": [rec], "error": rec.get("error")}