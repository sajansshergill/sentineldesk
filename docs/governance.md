# Governance

SentinelDesk is designed around one invariant: no write to a system of record
happens before human approval.

## Controls

- Extraction is schema-validated with nullable fields, so the system can refuse
  to guess missing settlement data.
- Reconciliation and scoring are deterministic service calls, not model prose.
- Summaries may only cite transaction IDs and rule IDs that were collected as
  evidence during the run.
- LangGraph interrupts before commit. The commit node only runs after an
  analyst submits `approved`, `approved_with_edits`, or `rejected`.
- CRM writes use a run ID as the idempotency key.

## Audit Trail

Each graph node appends a stage record with:

- agent name
- model or deterministic engine
- tool calls
- latency
- success/failure flags
- selected stage metadata such as score, citation count, or decision actor

The local MVP stores this in LangGraph memory. A production deployment should
move the same records to append-only storage with retention, export, and access
controls.

## Limits

All data is synthetic. Local evals are regression checks for code behavior, not
evidence that the system is suitable for regulated production use.
