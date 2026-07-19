# SentinelDesk

**Agentic transaction surveillance and CRM automation for correspondent banking operations.**

SentinelDesk is an end-to-end, human-in-the-loop automation pipeline that ingests settlement correspondence from foreign central banks, reconciles it against a transaction ledger, scores it for anomalies, drafts an analyst brief with cited evidence, and — after human approval — writes the outcome back to CRM.

Every agent hop is logged, evaluated, and gated. The build treats agent behavior as testable software, not as a demo.

---

## Why this exists

A correspondent-banking operations desk receives MT103/MT202-style settlement instructions and confirmations by email. Today an analyst reads each message, cross-checks it against the ledger, flags anything unusual, and updates the CRM by hand. The work is high-volume, low-variance, and expensive — and it is exactly the shape of problem agentic automation is supposed to solve.

The interesting engineering question is not "can an LLM read an email." It is: **can you put an agent loop into a regulated workflow and prove it behaves?**

SentinelDesk is my answer to that question.

---

## Architecture

```
┌──────────────┐
│  Outlook /   │  Copilot Studio agent
│  SharePoint  │  (mailbox + document triggers)
│  OneDrive    │
└──────┬───────┘
       │ custom connector (HTTPS)
       ▼
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator  ·  FastAPI + LangGraph state machine          │
│                                                              │
│   ingest ──► extract ──► reconcile ──► score ──► summarize   │
│                                                    │         │
│                                            ┌───────▼──────┐  │
│                                            │ APPROVAL     │  │
│                                            │ INTERRUPT    │  │
│                                            └───────┬──────┘  │
│                                                    ▼         │
│                                                 commit       │
└───────┬──────────────┬──────────────┬───────────────┬───────┘
        │              │              │               │
        ▼              ▼              ▼               ▼
  ┌──────────┐  ┌────────────┐  ┌───────────┐  ┌──────────┐
  │ Ledger   │  │  Anomaly   │  │  Bedrock  │  │   CRM    │
  │ service  │  │  service   │  │ (Claude)  │  │ service  │
  │ DuckDB   │  │ IsoForest  │  │ summaries │  │ Dataverse│
  │          │  │ + rules    │  │           │  │ Web API  │
  └──────────┘  └────────────┘  └───────────┘  └──────────┘
        │              │              │               │
        └──────────────┴──────┬───────┴───────────────┘
                              ▼
                    ┌──────────────────┐
                    │   Audit log      │
                    │  (append-only)   │
                    │  Postgres        │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Analyst console  │
                    │ Next.js + TS     │
                    └──────────────────┘
```

Hops communicate over Redis Streams with retry and dead-letter handling. The orchestrator is stateless; state lives in Postgres so a run can be resumed or replayed.

---

## The agent loop

| Stage | Agent | What it does | Failure mode it guards against |
|---|---|---|---|
| 1 | **Ingest** | Normalizes email + attachments from Copilot Studio payload; hashes raw input | Silent dedup loss |
| 2 | **Extract** | Pulls structured fields (value date, currency, amount, ordering/beneficiary institution, reference) from message body and attached documents | Hallucinated fields — schema-validated, refusal allowed |
| 3 | **Reconcile** | Matches extracted instruction against ledger records | False match on near-duplicate references |
| 4 | **Score** | Isolation Forest + deterministic rules engine | Model drift — rules provide a floor |
| 5 | **Summarize** | Claude via AWS Bedrock drafts an analyst brief citing specific ledger rows and rule hits | Unsupported claims — citations are validated against retrieved IDs |
| 6 | **Approve** | LangGraph interrupt. Human accepts, edits, or rejects | Autonomous write to a system of record |
| 7 | **Commit** | Writes activity + case record to Dynamics via Dataverse Web API | Partial write — idempotency key per run |

**No stage writes to a system of record without passing through stage 6.** That is the design constraint the whole thing is built around.

---

## Anomaly detection

Two layers, deliberately.

**Rules engine (deterministic, explainable):**
- Velocity — counterparty volume vs. trailing 30-day baseline
- Counterparty novelty — first-seen corridor between institution pair
- Round-number bias — amounts at suspicious precision
- Off-cycle timing — settlement outside the corridor's historical operating window
- Structuring signature — sequences below a reporting threshold

**Isolation Forest (statistical, catches the unenumerated):**
Trained on engineered features (log amount, corridor frequency, hour-of-day sine/cosine, days-since-last-seen, amount z-score within corridor).

The rules give you a defensible floor and an audit trail a compliance officer can read. The model catches what nobody wrote a rule for. Scores are combined, not averaged — a rule hit alone is sufficient to alert.

---

## Data

**All data is synthetic.** No real transaction data is used, stored, or referenced.

`data/generator/` produces ~50,000 transactions across 20 fictional central bank counterparties, with injected anomaly classes at controlled base rates:

| Class | Base rate | Detectable by |
|---|---|---|
| Duplicate settlement | 0.4% | rules |
| Amount transposition | 0.3% | rules + model |
| Novel counterparty corridor | 0.6% | rules |
| Off-cycle timing | 0.5% | model |
| Structuring pattern | 0.2% | rules |
| Unlabeled drift | ~1% | model only |

The generator is versioned and seeded. Every metric below is reproducible with `make data && make eval`.

---

## Evaluation

This is the part I care most about, and it comes from my QA/SDET background: **agent behavior is a test suite, not a vibe.**

`evals/` contains four gates, all wired into CI:

1. **Extraction accuracy** — field-level precision/recall against a hand-labeled 200-message holdout
2. **Anomaly detection** — precision/recall per injected class, plus false-positive rate at the production alerting threshold
3. **Trajectory eval** — percentage of runs completing the graph without human correction, scored against golden traces
4. **Citation integrity** — every claim in a generated brief must resolve to a ledger row or rule hit that was actually retrieved

CI fails the build when any gate regresses beyond tolerance. Metrics land in `evals/results/` and are tracked run-over-run.

> Results table is populated from the current eval run — see `evals/results/latest.md`. Numbers in this README are not hand-written.

---

## Stack

**Backend** — Python 3.11, FastAPI, LangGraph, Pydantic, DuckDB (ledger), Postgres (state + audit), Redis Streams
**ML** — scikit-learn (Isolation Forest), pandas, custom rules engine
**LLM** — AWS Bedrock (Anthropic Claude) for extraction and summarization
**Frontend** — Next.js 16 (App Router), TypeScript, TanStack Query, Tailwind
**Enterprise integration** — Microsoft Copilot Studio agent, custom connector, Dataverse Web API (Dynamics 365)
**CI/CD** — GitHub Actions, Docker, Azure Container Apps
**AI-assisted development** — Claude Code and Continue.dev used throughout; see `docs/ai-assisted-development.md` for what was delegated, what was hand-written, and what the review process looked like

---

## Analyst console

Next.js app at `apps/console/`:

- **Queue** — pending items ranked by anomaly score, with rule badges
- **Detail** — extracted fields beside the raw message, ledger match, rule hits, model score with feature attribution
- **Brief** — the drafted summary, with every citation clickable back to its source row
- **Diff** — proposed CRM write vs. current record state
- **Actions** — approve, edit-and-approve, reject with reason (reasons feed the eval set)
- **Audit** — full trace for any run: inputs, agents, tool calls, model versions, timings, human overrides

---

## Governance

Every run produces an append-only audit record containing:

```json
{
  "run_id": "uuid",
  "input_hash": "sha256",
  "stages": [
    {
      "agent": "extract",
      "model": "bedrock:anthropic.claude-...",
      "tool_calls": [...],
      "output_schema_valid": true,
      "confidence": 0.94,
      "latency_ms": 1180
    }
  ],
  "decision": "approved_with_edits",
  "human_actor": "analyst_id",
  "edits": [...],
  "committed_records": ["dynamics:incident:..."]
}
```

Audit records are immutable, queryable, and exportable. Model versions are pinned and recorded per run so a decision made six months ago can be explained.

---

## Running it

```bash
git clone https://github.com/sajansshergill/sentineldesk
cd sentineldesk

cp .env.example .env
make install
make data
make train
make api
```

In a second terminal:

```bash
make console
```

Console at `http://localhost:3000`. API docs at `http://localhost:8000/docs`.

Run local evals with:

```bash
make eval
```

Optional Streamlit client:

```bash
make streamlit
```

The Streamlit app runs from `streamlit_app.py` and expects a reachable API via
`SENTINEL_API_URL` (default `http://localhost:8000`). For Streamlit Cloud, deploy
`streamlit_app.py` and set `SENTINEL_API_URL` to the hosted FastAPI URL.

**Without cloud credentials:** the default `MODE=local` path runs with a deterministic local LLM fixture and an in-memory CRM sink. Anomaly detection, orchestration, evals, and the console all work against synthetic data. Extraction and summarization return fixture-backed JSON.

**Copilot Studio + Dynamics** require a Microsoft dev tenant and a Dynamics 365 trial. `docs/enterprise-setup.md` walks through connector registration, auth, and the Dataverse table schema. This path is documented but not reproducible without your own tenant.

---

## Scope and honest limits

Written down deliberately, because a portfolio project that oversells is worse than one that doesn't exist.

- **Synthetic data only.** The anomaly classes are ones I chose and injected. Real correspondent-banking anomalies are messier, rarer, and adversarial. Detection metrics here measure the pipeline, not real-world efficacy.
- **Not a compliance system.** No sanctions screening, no regulatory reporting, no SAR workflow. The governance layer is architecturally serious but has not been reviewed by anyone in financial crime compliance.
- **Domain depth is read, not lived.** I studied MT103/MT202 structure and nostro/vostro mechanics to make the synthetic corpus credible. I have not worked a correspondent-banking desk.
- **Databricks and Domino are not in this build.** The JD lists both. DuckDB covers the analytical workload at this scale, and I don't claim Domino experience — the closest thing I've done is MLflow-based experiment tracking, and I'd expect a ramp.
- **Single-tenant, single-region.** No multi-tenancy, no data residency handling.
- **Human approval is mandatory by design.** This is not a limitation I plan to remove. Autonomous writes to a system of record in this domain would be the wrong call.

---

## Repository layout

```
sentineldesk/
├── apps/
│   ├── api/                 # FastAPI orchestrator + LangGraph
│   └── console/             # Next.js analyst console
├── services/
│   ├── ledger/              # DuckDB transaction store + query API
│   ├── anomaly/             # rules engine + Isolation Forest
│   └── crm/                 # Dataverse Web API client
├── data/
│   ├── generator/           # synthetic transaction + message generator
│   └── labeled/             # hand-labeled extraction holdout
├── evals/
│   ├── extraction/
│   ├── anomaly/
│   ├── trajectory/
│   ├── citations/
│   └── results/
├── integrations/
│   └── copilot-studio/      # agent definition + custom connector spec
├── docs/
│   ├── architecture.md
│   ├── enterprise-setup.md
│   ├── governance.md
│   └── ai-assisted-development.md
└── .github/workflows/
```

---

## Author

**Sajan Shergill**
M.S. Data Science, Pace University (Seidenberg) · former Lead QA Engineer / SDET

[linkedin.com/in/sajanshergill](https://linkedin.com/in/sajanshergill) · [sajansshergill.github.io](https://sajansshergill.github.io) · sajansshergill@gmail.com
