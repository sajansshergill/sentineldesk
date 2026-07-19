"""Streamlit client for SentinelDesk.

Run standalone:

    streamlit run streamlit_app.py

Or point it at a deployed FastAPI backend:

    SENTINEL_API_URL=https://your-api.example.com streamlit run streamlit_app.py
"""

from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st


API_URL = os.getenv("SENTINEL_API_URL", "").rstrip("/")


st.set_page_config(page_title="SentinelDesk", page_icon="SD", layout="wide")
st.title("SentinelDesk")
st.caption("Human-in-the-loop transaction surveillance console")


def api_get(path: str) -> Any:
    response = requests.get(f"{API_URL}{path}", timeout=20)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict[str, Any]) -> Any:
    response = requests.post(f"{API_URL}{path}", json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


@st.cache_resource
def local_state():
    from apps.api.bootstrap import create_app_state

    return create_app_state()


def connect() -> tuple[str, dict[str, Any]]:
    if API_URL:
        try:
            return "api", api_get("/health")
        except requests.RequestException:
            pass

    state = local_state()
    return (
        "standalone",
        {
            "ok": True,
            "mode": "standalone",
            "ledger_count": state.ledger.count(),
        },
    )


def load_runs(mode: str) -> list[dict[str, Any]]:
    if mode == "api":
        return api_get("/runs")

    from apps.api.mapper import graph_snapshot_to_run

    state = local_state()
    return [graph_snapshot_to_run(snapshot, crm=state.crm) for snapshot in state.snapshots()]


def submit_decision(mode: str, run_id: str, payload: dict[str, Any]) -> None:
    if mode == "api":
        api_post(f"/runs/{run_id}/decision", payload)
        return

    from apps.api.bootstrap import decide_run

    decide_run(local_state(), run_id, payload)


def format_score(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.0%}"


with st.sidebar:
    st.header("Connection")
    st.code(API_URL or "standalone Streamlit mode")
    if st.button("Refresh runs", width="stretch"):
        st.cache_data.clear()


try:
    connection_mode, health = connect()
    st.success(
        f"{connection_mode.title()} connected: {health['mode']} mode, "
        f"{health['ledger_count']:,} ledger rows"
    )
    runs = load_runs(connection_mode)
except Exception as exc:  # pragma: no cover - Streamlit display path
    st.error(f"Could not start SentinelDesk Streamlit client: {exc}")
    st.stop()

if not runs:
    st.info("No runs are available yet.")
    st.stop()

run_options = {
    f"{run['run_id']} | {format_score(run.get('final_score'))} | {run.get('status')}": run
    for run in runs
}
selected_label = st.sidebar.selectbox("Run", list(run_options))
run = run_options[selected_label]

score = run.get("score") or {}
brief = run.get("brief") or {}
extraction = run.get("extraction") or {}
reconcile = run.get("reconcile") or {}

top = st.columns(4)
top[0].metric("Run", run["run_id"])
top[1].metric("Risk score", format_score(run.get("final_score")))
top[2].metric("Status", run.get("status", "unknown"))
top[3].metric("Decision", run.get("decision", "pending"))

st.subheader(brief.get("headline") or run["email"]["subject"])
st.write(brief.get("summary") or "No analyst brief is available.")

tab_extract, tab_score, tab_crm, tab_audit, tab_action = st.tabs(
    ["Extraction", "Score", "CRM Diff", "Audit", "Decision"]
)

with tab_extract:
    left, right = st.columns(2)
    left.write("Extracted instruction")
    left.json(extraction)
    right.write("Reconciliation")
    right.json(reconcile)
    st.write("Inbound message")
    st.text_area("Body", run["email"].get("body", ""), height=220, disabled=True)

with tab_score:
    st.metric("Model score", format_score(score.get("model_score")))
    rule_hits = score.get("rule_hits") or []
    if rule_hits:
        for hit in rule_hits:
            st.warning(f"{hit['rule_id']} ({hit['severity']}): {hit['detail']}")
    else:
        st.success("No deterministic rule hits.")
    st.write("Feature attribution")
    st.dataframe(score.get("feature_attribution") or [], width="stretch")

with tab_crm:
    st.dataframe(run.get("crm_diff") or [], width="stretch")

with tab_audit:
    st.dataframe(run.get("stages") or [], width="stretch")

with tab_action:
    actor = st.text_input("Actor", value="streamlit.analyst")
    reason = st.text_area("Reason or notes")
    summary_edit = st.text_area("Summary edit", value=brief.get("summary") or "", height=160)
    c1, c2, c3 = st.columns(3)
    payload_base = {
        "actor": actor,
        "reason": reason or None,
        "edits": {"summary": summary_edit} if summary_edit else {},
    }

    if c1.button("Approve", width="stretch"):
        submit_decision(connection_mode, run["run_id"], {**payload_base, "decision": "approved"})
        st.cache_data.clear()
        st.rerun()
    if c2.button("Approve with edits", width="stretch"):
        submit_decision(connection_mode, run["run_id"], {**payload_base, "decision": "approved_with_edits"})
        st.cache_data.clear()
        st.rerun()
    if c3.button("Reject", width="stretch"):
        submit_decision(connection_mode, run["run_id"], {**payload_base, "decision": "rejected"})
        st.cache_data.clear()
        st.rerun()
