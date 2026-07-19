"""Map graph state into the console API contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def graph_snapshot_to_run(snapshot: dict[str, Any], *, crm=None) -> dict[str, Any]:
    values = snapshot.get("values") or {}
    score = values.get("score") or {}
    brief = values.get("brief") or {}
    reconcile = values.get("reconcile") or {}
    decision = values.get("decision") or "pending"
    committed = values.get("committed")

    return {
        "run_id": values.get("run_id", ""),
        "status": _status(snapshot, values),
        "created_at": values.get("received_at") or _now(),
        "input_hash": values.get("input_hash") or "",
        "final_score": score.get("final_score"),
        "alerts": bool(score.get("alerts")),
        "decision": decision,
        "actor": values.get("actor"),
        "email": values.get("email") or _empty_email(),
        "extraction": values.get("extraction"),
        "reconcile": _map_reconcile(reconcile) if reconcile else None,
        "score": _map_score(score) if score else None,
        "brief": brief or None,
        "crm_diff": _crm_diff(values, crm=crm),
        "stages": [_map_stage(stage) for stage in values.get("stages", [])],
        "committed": committed,
    }


def _status(snapshot: dict[str, Any], values: dict[str, Any]) -> str:
    if values.get("committed"):
        return "rejected" if values.get("decision") == "rejected" else "committed"
    if values.get("halted_reason") or values.get("error"):
        return "halted"
    if "approval" in snapshot.get("next", []) or snapshot.get("interrupts"):
        return "pending_approval"
    return "pending_approval"


def _map_score(score: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": score.get("final_score", 0.0),
        "alert": bool(score.get("alerts")),
        "model_score": score.get("model_score", 0.0),
        "feature_attribution": [
            {"feature": name, "impact": min(abs(float(value)) / 5.0, 1.0)}
            for name, value in (score.get("attribution") or {}).items()
        ],
        "rule_hits": [_map_rule_hit(hit) for hit in score.get("hits", [])],
    }


def _map_rule_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": hit.get("rule_id", "R000_UNKNOWN"),
        "label": _title(hit.get("rule_id", "Rule hit")),
        "severity": hit.get("severity", "low"),
        "detail": hit.get("reason") or str(hit.get("detail") or ""),
    }


def _map_reconcile(reconcile: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": reconcile.get("status", "unmatched"),
        "txn_id": reconcile.get("txn_id"),
        "candidates": reconcile.get("candidates", []),
        "discrepancies": [
            {
                "field": item.get("field", "unknown"),
                "expected": item.get("message"),
                "observed": item.get("ledger"),
                "severity": "high" if item.get("field") == "amount" else "medium",
            }
            for item in reconcile.get("discrepancies", [])
        ],
    }


def _crm_diff(values: dict[str, Any], *, crm=None) -> list[dict[str, str]]:
    run_id = values.get("run_id", "")
    current = crm.get_case(run_id) if crm is not None and run_id else None
    brief = values.get("brief") or {}
    score = values.get("score") or {}
    extraction = values.get("extraction") or {}
    proposed_status = "Escalated" if score.get("alerts") else "Ready for closure"
    proposed_rating = "High" if score.get("alerts") else "Low"
    return [
        {
            "field": "case_status",
            "current": str((current or {}).get("case_status", "Open")),
            "proposed": proposed_status,
        },
        {
            "field": "risk_rating",
            "current": str((current or {}).get("risk_rating", "Unrated")),
            "proposed": proposed_rating,
        },
        {
            "field": "reference",
            "current": str((current or {}).get("reference", "")),
            "proposed": str(extraction.get("reference") or ""),
        },
        {
            "field": "analyst_summary",
            "current": str((current or {}).get("summary", "Awaiting review")),
            "proposed": str(brief.get("summary") or ""),
        },
    ]


def _map_stage(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": stage.get("agent", "unknown"),
        "model": stage.get("model"),
        "ok": bool(stage.get("ok", False)),
        "latency_ms": int(stage.get("latency_ms", 0)),
        "tool_calls": [
            call.get("tool", str(call)) if isinstance(call, dict) else str(call)
            for call in stage.get("tool_calls", [])
        ],
    }


def _empty_email() -> dict[str, Any]:
    return {"from": "", "to": "", "subject": "", "received_at": _now(), "body": "", "attachments": []}


def _title(value: str) -> str:
    return value.replace("_", " ").title()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
