"""Stage 1: ingest.

Normalises the Copilot Studio payload and hashes the raw input. The hash is
the dedup key and the audit anchor -- if the same email is delivered twice
(which mailbox connectors absolutely do), we want to know it is the same
bytes, not guess from the subject line.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ..schemas import InboundEmail
from ._stage import stage


def _hash_email(email: dict) -> str:
    canonical = json.dumps(
        {
            "from": email.get("from") or email.get("from_"),
            "subject": email.get("subject"),
            "body": email.get("body"),
            "attachments": [a.get("content", "") for a in email.get("attachments", [])],
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def ingest(state: dict) -> dict:
    with stage("ingest") as rec:
        raw = state["email"]
        email = InboundEmail.model_validate(raw)
        payload = email.model_dump(by_alias=True)
        rec["tool_calls"].append({"tool": "normalize_email", "ok": True})
        digest = _hash_email(payload)
        rec["input_hash"] = digest
        return {
            "email": payload,
            "input_hash": digest,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "stages": [rec],
            "evidence_ids": [],
        }
    return {"stages": [rec], "error": rec.get("error")}