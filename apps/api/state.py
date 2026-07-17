"""Graph state.

One TypedDict threaded through every node. Rules:
  - nodes return partial dicts; LangGraph merges them
  - nothing is mutated in place
  - `evidence_ids` is append-only and is the allowlist the citation
    validator checks against
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_sets(a: list[str], b: list[str]) -> list[str]:
    return sorted(set(a) | set(b))


class RunState(TypedDict, total=False):
    run_id: str
    input_hash: str
    received_at: str

    email: dict[str, Any]

    extraction: dict[str, Any] | None
    reconcile: dict[str, Any] | None
    score: dict[str, Any] | None
    brief: dict[str, Any] | None

    # append-only allowlist of things the summarizer may cite
    evidence_ids: Annotated[list[str], _merge_sets]

    # audit trail; each node appends one entry
    stages: Annotated[list[dict[str, Any]], operator.add]

    decision: str
    actor: str | None
    edits: dict[str, Any]
    committed: dict[str, Any] | None

    error: str | None
    halted_reason: str | None