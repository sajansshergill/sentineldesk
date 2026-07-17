"""LangGraph orchestrator.

    ingest -> extract -> reconcile -> score -> summarize -> [INTERRUPT] -> commit
                  |          |          |          |
                  +----------+----------+----------+--> halt (human review)

Two things worth defending:

1. **The interrupt is a graph node, not a UI convention.** LangGraph's
   checkpointer suspends execution before `commit` and will not resume
   without an explicit `Command(resume=...)`. You cannot get to a CRM write
   by forgetting to check a flag -- the graph physically stops. That is the
   difference between a control and a good intention.

2. **Halt is a first-class terminal state.** Any stage can route to `halt`
   by setting `halted_reason`. A halted run is not a failure; it is the
   system correctly declining to proceed and escalating to a person.
"""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from .agents import commit, extract, ingest, reconcile, score, summarize
from .state import RunState

HALT = "halt"

def _should_continue(state: RunState) -> str:
    """Route to halt if a stage flagged it. Checked after every node."""
    if state.get("halted_reason") or state.get("error"):
        return HALT
    return "continue"

def build_graph(*, llm, ledger, scorer, crm, checkpointer=None):
    """Wire the graph. Dependencies injected so evals can swap in fakes."""
    
    g = StateGraph(RunState)
    
    g.add_node("ingest", lambda s: ingest(s))
    g.add_node("extract", lambda s: extract(s, llm))
    g.add_node("reconcile", lambda s: reconcile(s, ledger))
    g.add_node("score", lambda s: score(s, ledger, scorer))
    g.add_node("summarize", lambda s: summarize(s, llm))
    g.add_node("approval", _approval_node)
    g.add_node("commit", lambda s: commit(s, crm))
    g.add_node(HALT, _halt_node)
    
    g.set_entry_point("ingest")
    
    for src, dst in (
        ("ingest", "extract"),
        ("extract", "reconcile"),
        ("reconcile", "score"),
        ("score", "summarize"),
    ):
        g.add_conditional_edges(src, _should_continue,
                                {"continue": dst, HALT: HALT})
        
    # summarize -> approval is unconditional: even a failed brief goes to a 
    # human. The one path we never take is summarize -> commit.
    g.add_edge("commit", END)
    g.add_edge(HALT, END)
    
    return g.compile(checkpointer=checkpointer or MemorySaver())

def _approval_node(state: RunState) -> dict:
    f"""The gate.
    
    `interrupt()` suspends the graph and surfaces the payload to the console.
    Execution resumes only when the API layer sends Command(resume={...}).
    The returned dict is whatever the human decided.
    """
    decision = interrupt({
        "run_id": state["run_id"],
        "headline": (state.get("brief") or {}).get("headline"),
        "summary": (state.get("brief") or {}).get("summary"),
        "citations": (state.get("brief") or {}).get("citations", []),
        "score": state.get("score"),
        "extraction": state.get("extraction"),
        "reconcile": state.get("reconcile"),
        "proposed_action": (state.get("brief") or {}).get("recommended_action"),
    })
    return {
        "decision": decision.get("decision", "rejected"),
        "actor": decision.get("actor"),
        "edits": decision.get("edits", {}),
        "stages": [{
            "agent": "approval",
            "model": None,
            "tool_calls": [],
            "ok": True,
            "decision": decision.get("decision"),
            "actor": decision.get("actor"),
            "latency_ms": 0,
        }],
    }

def _halt_node(state: RunState) -> dict:
    return {
        "stages": [{
            "agent": "halt",
            "model": None,
            "tool_calls": [],
            "ok": True,
            "reason": state.get("halted_reason") or state.get("error"),
            "latency_ms": 0,
        }],
        "decision": "pending",
    }
    
def new_run_id() -> str:
    return str(uuid.uuid4())

def start_run(graph, email: dict, run_id: str | None = None) -> tuple[str, dict]:
    """Run until the approval interrupt (or a halt). Returns (run_id, state)."""
    rid = run_id or new_run_id()
    cfg = {"configurable": {"thread_id": rid}}
    state = graph.invoke({"run_id": rid, "email": email,
                          "evidence_ids": [], "stages": []}, cfg)
    
def resume_run(graph, run_id: str, decision: dict) -> dict:
    """Resume a suspended run with a human decision."""
    cfg = {"configurable": {"thread_id": run_id}}
    return graph.invoke(Command(resume=decision), cfg)

def get_run(graph, run_id: str) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": run_id}}
    snap = graph.get_state(cfg)
    return {"values": snap.values, "next": list(snap.next),
            "interrupts": [i.value for i in getattr(snap, "interrupts", [])]}