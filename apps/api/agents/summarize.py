"""Stage 5: summarize.

The only stage where a model writes prose an analyst will read, which makes
it the only stage where hallucination has a direct path to a human decision.
Two controls:

  1. The prompt hands the model an explicit ALLOWED_CITATIONS list and forbids
     citing anything else.
  2. `_validate_citations` drops any citation outside state["evidence_ids"]
     and records the drop. Prompting is a request; validation is a guarantee.

If citations are dropped, the brief is still shown -- flagged -- because
hiding it would deny the analyst information. But the drop is audited, and
the citation eval gate fails the build if the rate creeps up.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from ..llm import LLMClient
from ..schemas import AnalystBrief
from ._stage import stage

SYSTEM = """SUMMARY_TASK
You write short surveillance briefs for correspondent banking analysts.

Return ONLY a JSON object: headline, summary, citations, recommended_action.
  - citations: [{"ref": "<id>", "kind": "rule"|"transaction"}]
  - recommended_action: "escalate" | "monitor" | "clear"

Rules:
- You may ONLY cite refs that appear in ALLOWED_CITATIONS. Citing anything
  else, including an id you infer or reconstruct, is a hard error.
- Every factual claim in `summary` must be supported by a cited ref.
- Do not speculate about intent, criminality, or the counterparty's motive.
  Describe what the controls found. An analyst decides what it means.
- If the evidence is thin, say so plainly and recommend "monitor".
- Under 120 words.
"""


def _user_prompt(state: dict) -> str:
    return json.dumps({
        "extraction": state.get("extraction"),
        "reconcile": state.get("reconcile"),
        "score": state.get("score"),
        "ALLOWED_CITATIONS": state.get("evidence_ids", []),
    }, indent=2)


def _validate_citations(brief: AnalystBrief, allowed: set[str]) -> tuple[AnalystBrief, list[str]]:
    kept, dropped = [], []
    for c in brief.citations:
        (kept if c.ref in allowed else dropped).append(c)
    brief.citations = kept
    return brief, [c.ref for c in dropped]


def summarize(state: dict, llm: LLMClient) -> dict:
    with stage("summarize", model=llm.model_id) as rec:
        resp = llm.complete(SYSTEM, _user_prompt(state), max_tokens=600,
                            temperature=0.0)
        rec["tool_calls"].append({"tool": "llm.complete", "task": "summarize"})
        rec["input_tokens"] = resp.input_tokens
        rec["output_tokens"] = resp.output_tokens

        try:
            brief = AnalystBrief.model_validate(resp.json())
        except (ValidationError, ValueError) as exc:
            rec["ok"] = False
            rec["error"] = f"brief_schema_invalid: {exc}"
            return {"stages": [rec], "brief": None,
                    "halted_reason": "Brief did not validate; human review."}

        allowed = set(state.get("evidence_ids", []))
        brief, dropped = _validate_citations(brief, allowed)
        brief.model_id = llm.model_id

        rec["output_schema_valid"] = True
        rec["citations_kept"] = len(brief.citations)
        rec["citations_dropped"] = dropped
        if dropped:
            rec["ok"] = False
            rec["error"] = f"unsupported_citations_dropped: {dropped}"

        return {"stages": [rec], "brief": brief.model_dump(mode="json")}
    return {"stages": [rec], "error": rec.get("error")}