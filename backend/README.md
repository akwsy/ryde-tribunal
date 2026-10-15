# Ryde Tribunal — Backend

FastAPI dispute-adjudication service: orchestration + model components (Rider Advocate,
Driver Advocate, Evidence Auditor, Judge) that reason **from the individual case**, policy loading, evidence
handling with semantic citation validation, verified-over-unverified precedence, external-info
quarantine, escalation, persistence, dashboard metrics, and reviewer approve/override. Categories
`route_deviation` and `no_show_charge` have automated policy flows; the other filing categories
can be sent to human review. The integrity rules are documented in `docs/04-integrity-rules.md`.

## Setup

Python 3.12 via `uv` (repo-pinned in `.python-version`).

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -e '.[dev]'
```

## Environment

Copy the repo-root `.env.example` to `backend/.env` and fill values locally (`.env` is gitignored;
never commit a key). The variables the backend reads:

From `backend/`: `cp ../.env.example .env`. The backend imports the database-owned reader and
importer directly from this monorepo, so direct backend commands require `PYTHONPATH=..`.
The root `run-local.sh` sets that path automatically.

| var | meaning |
|---|---|
| `MODEL_PROVIDER` | `deterministic_mock` (offline, CI default) or `openai_compatible` |
| `MODEL_BASE_URL` / `MODEL_NAME` / `MODEL_API_KEY` | required only for `openai_compatible` |
| `MODEL_PROVIDER_NAME` | optional user-facing LLM provider label; known Google/OpenAI hosts are named automatically |
| `POLICY_VERSION` | `ryde-policy-1.0.0` |
| `POLICY_PATH` | optional override of the policy JSON location |
| `JUDGING_CONFIG_PATH` | optional override of `config/judging.json` (precedent origin weights, recency half-life, fraud influence) |
| `ESCALATION_CONFIDENCE_THRESHOLD` | D-09, default `0.70` |
| `HIGH_IMPACT_AMOUNT_CENTS` | D-10, default `2500` |
| `GOODWILL_CAP_CENTS` | D-11, default `1500` |
| `EXTERNAL_INFO_ENABLED` | I-8 external source, default `false` |
| `CURRENCY` / `TIMEZONE` | `SGD` / `Asia/Singapore` |

The Judge applies policy before precedents. Configured precedence weights give reviewer-approved
rulings more credibility than model proposals and decay older examples using the configured half-life.
Fraud history can affect scrutiny of unsupported advocate claims, but it is not an escalation trigger
by itself and cannot override verified records. Every escalation summary describes what verified
evidence shows and what it does not establish.

## Run

```bash
PYTHONPATH=.. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Reader selection is by config. With no `READ_DATABASE_DSN` set the server wires
`PendingDatabaseReader` and data routes return `database_unavailable` (no fabricated rulings).
Set the read-only DSN to connect to Postgres:

```bash
export READ_DATABASE_DSN="postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal"
PYTHONPATH=.. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000   # /api/v1/health -> {"database":"ok"}
```

`READ_DATABASE_DSN` is a PLAIN psycopg DSN (not `postgresql+psycopg://`) connecting as the
read-only role `ryde_backend_readonly` (SELECT only on `ride_data` / `case_archive`). The
backend's own `tribunal` schema uses a separate writable connection (`TRIBUNAL_DATABASE_DSN`).

## Integration tests (real Postgres)

PostgreSQL tests must use a disposable database ending in `_test` or `_tests`. Never point them
at the persistent app database `ryde_tribunal`. Start a local Postgres instance, then from the
repo root seed and migrate a disposable database with:

```bash
export RYDE_TEST_DATABASE_URL="postgresql://allan@localhost:5432/ryde_tribunal_test"
export POSTGRES_ADMIN_URL="postgresql://allan@localhost:5432/postgres"
cd database
uv run pytest -q
```

Then run the backend adapter checks against that seeded test database:

```bash
cd ../backend
export RYDE_TEST_READ_DSN="postgresql://ryde_backend_readonly:ryde_backend_readonly@localhost:5432/ryde_tribunal_test"
uv run pytest tests/test_integration_postgres.py -v
```

The integration suite files and adjudicates seeded rides, verifies measurements and evidence
against source rows, proves the read-only role cannot write, and checks the `database_unavailable`
path. The test module rejects database names that do not end in `_test` or `_tests`.

## Migrations (backend owns the `tribunal` schema)

Per `docs/02-api-contract.md` §6, the backend owns and migrates the `tribunal` schema
(`case_*`, `model_work_*`, `ruling_*`, `case_history`, `idempotency_keys`). Migrations are
Alembic, under `backend/migrations/`. The backend's DB role has `SELECT`-only on `ride_data`
and `case_archive` — it never migrates or writes those.

```bash
export DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5432/ryde_tribunal
uv run alembic upgrade head      # create tribunal schema + tables
uv run alembic downgrade base    # drop the backend tables
```

The `idempotency_keys` UNIQUE constraint is the DB-level concurrency guarantee (contract §2).
For durable cases, model work, evidence bundles, results, approvals, and history, set
`TRIBUNAL_DATABASE_DSN` to a writable DSN for the backend-owned `tribunal` schema before starting
the service. The server then selects `PostgresResultStore`; without it, tests and local offline
runs use the in-process `ResultStore`. `DATABASE_URL` above is only for running Alembic.
Apply the current backend migration head before starting the backend;
that migration creates and grants the shared `ride_data.imported_evidence_id_seq`. The login
behind `TRIBUNAL_DATABASE_DSN` must be a member of the no-login `ryde_backend_writer` group role
so live case filings can allocate EV IDs without granting writes to `ride_data` or `case_archive`.
Keep the legacy `tribunal.evidence_id_seq` in place until the one-time global-ID remap captures its
high-water mark and advances the shared sequence. The old sequence remains dormant after backend
code switches to the shared allocator.

Model-proposed rulings are stored separately from reviewer-approved rulings. Approval and override
append history and retain the original model proposal. The Judge receives prior same-category
tribunal outcomes as advisory context, with reviewer-approved outcomes labelled higher credibility.

## Test

```bash
uv run pytest -q          # full suite, offline, on the deterministic_mock provider
```

## Switching providers

Selection is by env (`MODEL_PROVIDER`) via `app/providers/factory.py`:
- `deterministic_mock` — fully offline, deterministic, labelled `deterministic-mock`; a ruling
  it touched carries `synthetic_reasoning: true` (I-6). What CI runs.
- `openai_compatible` — POSTs to an OpenAI-style `/chat/completions` endpoint; labelled `llm`.
  It is invoked only after the rules-first Judge remains uncertain through three advocate repair
  rounds. Clear source-backed route and cancellation cases are resolved by `rules_first.py` with
  no model calls. The independent code validator checks every proposal before it can be treated as
  an automatic resolution. The local configuration uses Gemini 3.1 Flash-Lite; see
  [submission readiness](../docs/submission/READINESS.md).

The orchestration does not change between providers — only the seam that turns a prompt into a
component's structured conclusion.

## Proving the integrity tests bite

The suite includes `tests/test_i1_red_precomputed_verdict.py`, which demonstrates the I-1
guards reject a reintroduced verdict. This was also verified end-to-end by hand: injecting a
`recommended_ruling_type` field into `PolicyContext` turns
`tests/test_i1_no_precomputed_verdict.py::test_policycontext_has_no_verdict_field` RED with
`PolicyContext.recommended_ruling_type is verdict-shaped`, and removing it returns the suite to
green. The integrity tests are not decoration.

## Architecture

```
app/
  settings.py              env config (decision params, never policy remedies)
  domain/                  enums + Money + visibility rules
  policy/
    context.py             PolicyContext — frozen, structurally verdict-incapable (I-1)
    loader.py              versioned JSON policy loader (D-18, one source of truth)
    evaluator.py           case facts -> applicable rule ids + measurements ONLY (I-1)
  evidence/
    models.py              Evidence, Verification, Citation
    citation.py            CitationValidator — 6 semantic checks (I-3)
    precedence.py          EvidencePrecedence — verified > unverified per question (I-7)
    external.py            ExternalFindings quarantine (I-8)
  providers/
    base.py                ModelProvider seam + provider metadata (I-6)
    deterministic_mock.py  offline case-specific advocate/judge (I-5, I-6)
    openai_compatible.py   real-LLM adapter (provider listing verified; generation blocked)
    factory.py             env selection (D-04)
  models/components.py     Model-backed advocate + final AI Judge (validate citations, stamp provider)
  models/evidence_auditor.py  audit advocate claims against evidence
  models/fraud_detector.py   produce a case-specific fraud-risk assessment
  models/judging_config.py   configurable precedent and fraud weights
  orchestration/
    facts.py               assemble case facts + evidence bundle (system records from the 11 read
                           accessors + party submissions), assemble_evidence_bundle
    escalation.py          RP-ESC-*, D-09/10/11, RP-SAFETY-001, human-review summary
    rules_first.py         narrow clear-case decisions + evidence-only advocate repair summaries
    official_gate.py       independent final code validation of policy, evidence, and remedies
    orchestrator.py        rules-first routing, three repair rounds, selective AI review and trace
  persistence/
    reader.py              the 11 READ-ONLY DB accessors as a Protocol + outcome-free records (I-2)
    models.py              SQLAlchemy models for the backend-owned `tribunal` schema (§6)
    store.py               in-process test store and concurrency-safe idempotency
    postgres_store.py      durable tribunal store for live local use
  api/
    container.py           dependency wiring (swap reader/provider/external; injects store)
    app.py                 app wiring and dispute, evidence, archive, and trip endpoints
    archive_presenter.py   convert stored historical cases to read-only API results
    company_import.py      bounded ZIP upload and validated company-data import endpoint
    metrics_routes.py      dashboard metric endpoints and range validation
    metrics_helpers.py     pure date, grouping, and time-series calculations
  main.py                  ASGI entrypoint

migrations/                Alembic migration set for the `tribunal` schema
tests/                     §7 flow + failure + integrity suites; fixtures/ (reader, cases, policy)
tools/gen_handoff.py       emits handoff/openapi.json + sample CaseResults
handoff/                   generated artifacts for the lead agent
```

See `ASSUMPTIONS.md` for material assumptions and open questions.
