"""Graph nodes. Each is a pure-ish function: state in, partial state out.

Contract every node honours:
  - never raise; capture failure into state["error"] and let the graph route
  - append exactly one entry to state["stages"] for the audit trail
  - only widen state["evidence_ids"] with IDs actually retrieved
"""

from .ingest import ingest
from .extract import extract
from .reconcile import reconcile
from .score import score
from .summarize import summarize
from .commit import commit

__all__ = ["ingest", "extract", "reconcile", "score", "summarize", "commit"]