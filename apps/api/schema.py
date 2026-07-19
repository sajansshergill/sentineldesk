"""Wire + internal schemas.

The extraction schema is the load-bearing one. It is validated strictly, and
every field is Optional with an explicit `null` allowed, because the single
most dangerous failure mode in this pipeline is an LLM inventing a value
rather than admitting it could not find one. Refusal must be representable.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class MessageType(str, Enum):
    MT103 = "MT103"
    MT202 = "MT202"
    UNKNOWN = "UNKNOWN"


class Attachment(BaseModel):
    filename: str
    content_type: str = "text/plain"
    content: str = ""


class InboundEmail(BaseModel):
    """What Copilot Studio posts to us."""

    from_: str = Field(alias="from")
    to: str
    subject: str
    received_at: str
    body: str
    attachments: list[Attachment] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ExtractedInstruction(BaseModel):
    """Structured settlement fields pulled from an email.

    All fields nullable on purpose. `confidence` and `unresolved` are how the
    agent says "I don't know" instead of guessing.
    """

    reference: str | None = None
    sender_bic: str | None = None
    receiver_bic: str | None = None
    currency: str | None = None
    amount: float | None = None
    value_date: str | None = None
    message_type: MessageType = MessageType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    unresolved: list[str] = Field(default_factory=list)
    source: Literal["body", "attachment", "mixed", "none"] = "none"

    @field_validator("sender_bic", "receiver_bic")
    @classmethod
    def _bic_shape(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if not (8 <= len(v) <= 11) or not v.isalnum():
            raise ValueError(f"implausible BIC: {v!r}")
        return v

    @field_validator("currency")
    @classmethod
    def _ccy(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError(f"implausible currency: {v!r}")
        return v

    @field_validator("amount")
    @classmethod
    def _amt(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v <= 0 or v > 1e15:
            raise ValueError(f"implausible amount: {v}")
        return round(float(v), 2)


class ReconcileResult(BaseModel):
    status: Literal["matched", "mismatch", "unmatched"]
    txn_id: str | None = None
    candidates: list[str] = Field(default_factory=list)
    discrepancies: list[dict[str, Any]] = Field(default_factory=list)


class Citation(BaseModel):
    """A claim's supporting evidence. `ref` must be a txn_id or a rule_id
    that was actually retrieved during this run -- validated, not trusted."""

    ref: str
    kind: Literal["transaction", "rule"]


class AnalystBrief(BaseModel):
    headline: str
    summary: str
    citations: list[Citation] = Field(default_factory=list)
    recommended_action: Literal["escalate", "monitor", "clear"] = "monitor"
    model_id: str = "unknown"


class Decision(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"
    PENDING = "pending"


class ApprovalRequest(BaseModel):
    run_id: str
    decision: Decision
    actor: str
    edits: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class RunSummary(BaseModel):
    run_id: str
    status: str
    created_at: str
    final_score: float | None = None
    alerts: bool = False
    headline: str | None = None
    decision: Decision = Decision.PENDING


class RunCreateRequest(BaseModel):
    email: InboundEmail
    run_id: str | None = None


class HealthResponse(BaseModel):
    ok: bool = True
    mode: str
    ledger_count: int