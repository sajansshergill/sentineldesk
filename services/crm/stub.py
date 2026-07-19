"""In-memory CRM sink.

Honours the same idempotency contract as the Dataverse client, so the
idempotency behaviour itself is testable without a Dynamics tenant. That
matters: the double-write bug is the one you cannot afford to discover in
production, and it is exactly the one a stub can catch.
"""

from __future__ import annotations

from datetime import datetime, timezone


class StubCRM:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.write_count = 0

    def upsert_case(self, idempotency_key: str, **fields) -> dict:
        self.write_count += 1
        if idempotency_key in self.records:
            return {**self.records[idempotency_key], "status": "already_exists",
                    "deduped": True}
        record = {
            "record_id": f"stub:incident:{idempotency_key[:8]}",
            "status": "created",
            "deduped": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in fields.items() if v is not None},
        }
        self.records[idempotency_key] = record
        return record

    def get_case(self, idempotency_key: str) -> dict | None:
        return self.records.get(idempotency_key)