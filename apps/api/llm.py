"""LLM clients.

The default local client is deterministic and credential-free. It gives the
LangGraph pipeline the same JSON contract as a hosted model while keeping the
MVP runnable on a laptop.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int

    def json(self) -> dict[str, Any]:
        return json.loads(self.content)


class LLMClient:
    model_id = "local-fixture-1.0"

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResponse:
        raise NotImplementedError


class LocalLLMClient(LLMClient):
    model_id = "local-fixture-1.0"

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResponse:
        del max_tokens, temperature
        if "EXTRACTION_TASK" in system:
            payload = _extract_payload(prompt)
        elif "SUMMARY_TASK" in system:
            payload = _summary_payload(prompt)
        else:
            payload = {}

        content = json.dumps(payload)
        return LLMResponse(
            content=content,
            input_tokens=max(1, len(prompt.split())),
            output_tokens=max(1, len(content.split())),
        )


def _extract_payload(prompt: str) -> dict[str, Any]:
    attachment = _between(prompt, "<<<ATTACHMENT>>>", "<<<END_ATTACHMENT>>>")
    body = _between(prompt, "<<<BODY>>>", "<<<END_BODY>>>")
    text = attachment or body

    mt_amount = re.search(
        r":32A:(?P<date>\d{6})(?P<currency>[A-Z]{3})(?P<amount>[0-9,.]+)",
        text,
    )
    reference = _first_match(text, [r":20:([A-Z0-9-]+)", r"Our reference(?: is|:)\s*([A-Z0-9-]+)"])
    sender = _first_match(text, [r":52A:([A-Z0-9]{8,11})", r"Ordering institution:.*\(([A-Z0-9]{8,11})\)"])
    receiver = _first_match(
        text,
        [r":58A:([A-Z0-9]{8,11})", r"Beneficiary institution:.*\(([A-Z0-9]{8,11})\)"],
    )
    message_type = _first_match(text, [r"\{2:I(103|202)", r"Message type:\s*(MT103|MT202)"])

    currency = None
    amount: float | None = None
    value_date = None
    if mt_amount:
        currency = mt_amount.group("currency")
        amount = float(mt_amount.group("amount").replace(",", "."))
        value_date = _swift_date(mt_amount.group("date"))
    else:
        amount_match = re.search(r"\b([A-Z]{3})\s*([0-9][0-9,]*\.?[0-9]*)", text)
        if not amount_match:
            amount_match = re.search(r"\b([0-9][0-9,]*\.?[0-9]*)\s*([A-Z]{3})\b", text)
            if amount_match:
                amount = float(amount_match.group(1).replace(",", ""))
                currency = amount_match.group(2)
        else:
            currency = amount_match.group(1)
            amount = float(amount_match.group(2).replace(",", ""))
        value_date = _first_match(
            text,
            [
                r"value(?: date)?\s+(\d{4}-\d{2}-\d{2})",
                r"value(?: date)?\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
            ],
        )
        value_date = _normalize_date(value_date)

    if message_type in {"103", "202"}:
        message_type = f"MT{message_type}"

    payload = {
        "reference": reference,
        "sender_bic": sender,
        "receiver_bic": receiver,
        "currency": currency,
        "amount": amount,
        "value_date": value_date,
        "message_type": message_type or "UNKNOWN",
        "confidence": 0.92,
        "unresolved": [],
        "source": "attachment" if attachment else "body",
    }
    payload["unresolved"] = [k for k in ("reference", "sender_bic", "receiver_bic", "currency", "amount", "value_date") if payload[k] is None]
    if payload["unresolved"]:
        payload["confidence"] = 0.55
    return payload


def _summary_payload(prompt: str) -> dict[str, Any]:
    data = json.loads(prompt)
    extraction = data.get("extraction") or {}
    reconcile = data.get("reconcile") or {}
    score = data.get("score") or {}
    allowed = list(data.get("ALLOWED_CITATIONS") or [])

    final_score = float(score.get("final_score") or 0.0)
    alerts = bool(score.get("alerts"))
    reference = extraction.get("reference") or "unknown reference"
    amount = extraction.get("amount")
    currency = extraction.get("currency") or ""
    status = reconcile.get("status") or "unmatched"

    if alerts:
        headline = f"Alert on {reference}: {status} settlement"
        action = "escalate"
    elif status == "matched":
        headline = f"Matched settlement {reference}"
        action = "monitor"
    else:
        headline = f"Review needed for {reference}"
        action = "monitor"

    amount_text = f"{currency} {amount:,.2f}" if isinstance(amount, (int, float)) else "the extracted amount"
    summary = (
        f"The instruction for {reference} covers {amount_text}. Reconciliation status is "
        f"{status}, and the combined surveillance score is {final_score:.2f}. "
        f"{'Rule or model signals require escalation.' if alerts else 'No high-risk signal was detected.'}"
    )
    citations = [{"ref": ref, "kind": "rule" if str(ref).startswith("R") else "transaction"} for ref in allowed[:3]]
    return {
        "headline": headline,
        "summary": summary,
        "citations": citations,
        "recommended_action": action,
    }


def _between(text: str, start: str, end: str) -> str:
    if start not in text:
        return ""
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip().upper()
    return None


def _swift_date(value: str) -> str:
    return datetime.strptime(value, "%y%m%d").date().isoformat()


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value
