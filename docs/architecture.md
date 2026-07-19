# Architecture

SentinelDesk is a local, human-in-the-loop transaction surveillance MVP. It
uses synthetic settlement emails, a DuckDB-backed ledger, deterministic anomaly
rules, an Isolation Forest score, a LangGraph approval interrupt, and a Next.js
analyst console.

## Local Data Flow

```mermaid
flowchart LR
  generator["Synthetic generator"] --> ledger["DuckDB ledger"]
  generator --> corpus["Email corpus"]
  corpus --> api["FastAPI API"]
  ledger --> graph["LangGraph pipeline"]
  api --> graph
  graph --> approval["Approval interrupt"]
  approval --> crm["Stub CRM"]
  api --> console["Next.js console"]
```

## Runtime Components

- `apps/api` contains the FastAPI app and LangGraph orchestration.
- `services/ledger` owns transaction storage and reconciliation.
- `services/anomaly` owns rules, feature engineering, model training, and scoring.
- `services/crm` provides a local CRM stub and an optional Dataverse client.
- `apps/console` provides the analyst review interface.
- `evals` contains local regression checks for extraction, anomaly detection, trajectory, and citations.

## Local Mode

`MODE=local` is the default. It uses:

- `LocalLLMClient` for deterministic extraction and brief generation.
- `StubCRM` for idempotent CRM writes.
- In-memory DuckDB unless `SENTINEL_LEDGER_PATH` is set.
- Synthetic data under `var/`.

The MVP intentionally avoids requiring Redis, Postgres, Bedrock, or Dataverse
credentials. Those are integration paths, not local runtime blockers.
