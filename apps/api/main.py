"""FastAPI entrypoint for the local SentinelDesk MVP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .bootstrap import AppState, create_app_state, decide_run, start_email_run
from .mapper import graph_snapshot_to_run
from .schema import HealthResponse, RunCreateRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.sentinel = create_app_state()
    yield


app = FastAPI(
    title="SentinelDesk API",
    version="1.0.0",
    description="Local FastAPI orchestrator for SentinelDesk analyst workflows.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> dict[str, Any]:
    state = _state()
    return {"ok": True, "mode": state.mode, "ledger_count": state.ledger.count()}


@app.get("/runs")
def list_runs() -> list[dict[str, Any]]:
    state = _state()
    return [
        graph_snapshot_to_run(snapshot, crm=state.crm)
        for snapshot in sorted(
            state.snapshots(),
            key=lambda item: (item.get("values") or {}).get("received_at", ""),
            reverse=True,
        )
    ]


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    state = _state()
    if run_id not in state.run_ids:
        raise HTTPException(status_code=404, detail="run not found")
    snapshot = state.graph.get_state({"configurable": {"thread_id": run_id}})
    return graph_snapshot_to_run({"values": snapshot.values, "next": list(snapshot.next), "interrupts": []}, crm=state.crm)


@app.post("/runs")
def create_run(payload: RunCreateRequest) -> dict[str, Any]:
    state = _state()
    return start_email_run(state, payload.email.model_dump(by_alias=True), run_id=payload.run_id)


@app.post("/runs/{run_id}/decision")
def submit_decision(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = _state()
    if run_id not in state.run_ids:
        raise HTTPException(status_code=404, detail="run not found")
    decision = {
        "decision": payload.get("decision", "rejected"),
        "actor": payload.get("actor", "analyst.local"),
        "edits": payload.get("edits") or {},
        "reason": payload.get("reason"),
    }
    return decide_run(state, run_id, decision)


def _state() -> AppState:
    sentinel = getattr(app.state, "sentinel", None)
    if sentinel is None:
        raise HTTPException(status_code=503, detail="application state is not ready")
    return sentinel
