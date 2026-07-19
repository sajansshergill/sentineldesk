# AI-Assisted Development

This repository was completed with agent assistance, but the code paths remain
ordinary, inspectable software.

## Delegated Work

- Project scaffolding and local MVP wiring.
- FastAPI route setup and response mapping for the console.
- Deterministic local LLM fixture implementation.
- Lightweight eval runner and documentation drafts.

## Human Review Focus

Review should focus on:

- graph routing and the approval-before-commit invariant
- schema validation behavior
- idempotent CRM writes
- eval thresholds and whether they match the intended risk posture
- README claims versus implemented behavior

## Guardrails

The local MVP deliberately uses synthetic data and local stubs. Any real
financial, CRM, or identity-provider integration should receive separate
security and compliance review before use outside a demo environment.
