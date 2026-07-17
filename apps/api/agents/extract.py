"""Stage 2: extract.

The prompt does three things that matter:

  1. Fences the body and attachment so the model knows which is which.
  2. Explicitly names the distractors (disclaimer reference numbers,
     forwarded batch totals) and forbids extracting from them. Without this
     both the regex baseline and the LLM reach for the decoy.
  3. Requires `null` + an entry in `unresolved` for anything not found.
     A model that cannot say "I don't know" will invent a BIC.

Output is schema-validated. A validation failure is a *hard stop*, not a
retry-until-it-parses loop -- if the model cannot produce a well-formed
instruction, a human should see the raw email.
"""

from __future__ import annotations

from pydantic import ValidationError

from ..llm import LLMClient
from ..schemas import ExtractedInstruction
from ._stage import stage

SYSTEM = """EXTRACTION_TASK
You extract settlement instruction fields from correspondent banking email.

Return ONLY a JSON object with these keys:
  reference, sender_bic, receiver_bic, currency, amount, value_date,
  message_type, confidence, unresolved, source

Rules:
- amount: a number, no separators. value_date: YYYY-MM-DD. message_type: MT103, MT202, or UNKNOWN.
- If a field is not present, set it to null AND list its name in `unresolved`.
  Never guess. An invented BIC or amount is worse than a null.
- NEVER extract values from the legal disclaimer or from any forwarded/quoted
  message below an "-----Original Message-----" marker. Those contain decoy
  reference numbers and batch totals that are NOT this instruction's values.
- If an attachment MT block is present, it is authoritative over the body.
  Set source to "attachment", "body", or "mixed" accordingly.
- confidence: your calibrated 0-1 estimate that every non-null field is correct.
"""


def _user_prompt(email: dict) -> str:
    att = ""
    for a in email.get("attachments", []):
        att += a.get("content", "") + "\n"
    parts = [f"Subject: {email.get('subject', '')}",
             f"From: {email.get('from', '')}",
             "", "<<<BODY>>>", email.get("body", ""), "<<<END_BODY>>>"]
    if att.strip():
        parts += ["", "<<<ATTACHMENT>>>", att, "<<<END_ATTACHMENT>>>"]
    return "\n".join(parts)


def extract(state: dict, llm: LLMClient) -> dict:
    with stage("extract", model=llm.model_id) as rec:
        prompt = _user_prompt(state["email"])
        resp = llm.complete(SYSTEM, prompt, max_tokens=800, temperature=0.0)
        rec["tool_calls"].append({"tool": "llm.complete", "task": "extract"})
        rec["input_tokens"] = resp.input_tokens
        rec["output_tokens"] = resp.output_tokens

        try:
            payload = resp.json()
            inst = ExtractedInstruction.model_validate(payload)
        except (ValidationError, ValueError) as exc:
            rec["ok"] = False
            rec["error"] = f"extraction_schema_invalid: {exc}"
            rec["output_schema_valid"] = False
            return {
                "stages": [rec],
                "extraction": None,
                "error": "extraction_schema_invalid",
                "halted_reason": "Extraction did not validate; routing to human.",
            }

        rec["output_schema_valid"] = True
        rec["confidence"] = inst.confidence
        return {"stages": [rec], "extraction": inst.model_dump(mode="json")}
    return {"stages": [rec], "error": rec.get("error")}