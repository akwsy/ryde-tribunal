# Ryde Tribunal — Backend (Phase Zero)

FastAPI dispute-adjudication service: orchestration + three model components (Rider Advocate,
Driver Advocate, Judge) that reason **from the individual case**, policy loading, evidence
handling with semantic citation validation, verified-over-unverified precedence, external-info
quarantine, escalation, persistence, and reviewer approve/override. Categories
`route_deviation` and `no_show` end to end. All acceptance criteria in `docs/04-integrity-rules.md`
are enforced by tests.

## Setup

Python 3.12 via `uv` (repo-pinned in `.python-version`).

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -e '.[dev]'
```

## Environment

Copy the repo-root `.env.example` to `.env` and fill values locally (`.env` is gitignored;
never commit a key). The variables the backend reads:

| var | meaning |
|---|---|
| `MODEL_PROVIDER` | `deterministic_mock` (offline, CI default) or `openai_compatible` |
| `MODEL_BASE_URL` / `MODEL_NAME` / `MODEL_API_KEY` | required only for `openai_compatible` |
| `POLICY_VERSION` | `ryde-policy-0.1.0` |
| `POLICY_PATH` | optional override of the policy JSON location |
| `ESCALATION_CONFIDENCE_THRESHOLD` | D-09, default `0.70` |
| `HIGH_IMPACT_AMOUNT_CENTS` | D-10, default `2500` |
| `GOODWILL_CAP_CENTS` | D-11, default `1500` |
| `FRAUD_RISK_ESCALATION_THRESHOLD` | D-10, default `0.60` |
| `EXTERNAL_INFO_ENABLED` | I-8 external source, default `false` |
| `CURRENCY` / `TIMEZONE` | `SGD` / `Asia/Singapore` |

## Run

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The database specialist's Postgres reader is not integrated yet, so a live server returns
`database_unavailable` on data routes until the reader is wired at
`app.api.container.build_container` (see ASSUMPTIONS A-8). This is intentional: no fabricated
rulings.

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
The request path in Phase Zero uses the in-process `ResultStore`; the SQLAlchemy-backed store
(models in `app/persistence/models.py`) swaps in behind the same surface at integration.

## Test

```bash
uv run pytest -q          # full suite, offline, on the deterministic_mock provider
```

## Switching providers

Selection is by env (`MODEL_PROVIDER`) via `app/providers/factory.py`:
- `deterministic_mock` — fully offline, deterministic, labelled `deterministic-mock`; a ruling
  it touched carries `synthetic_reasoning: true` (I-6). What CI runs.
- `openai_compatible` — POSTs to an OpenAI-style `/chat/completions` endpoint; labelled `llm`.
  Ready but untested against a live endpoint in Phase Zero (no credentials). The owner supplies
  base URL / model / key at approval (D-04).

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
    openai_compatible.py   real-LLM adapter (ready, untested live)
    factory.py             env selection (D-04)
  models/components.py     Advocate + Judge (prompt, validate citations, stamp provider)
  orchestration/
    facts.py               assemble case facts + evidence from the 9 accessors
    escalation.py          RP-ESC-*, D-09/10/11, RP-SAFETY-001, human-review summary
    orchestrator.py        run_case: the deterministic workflow around model conclusions
  persistence/
    reader.py              the 8 READ-ONLY DB accessors as a Protocol + outcome-free records (I-2)
    models.py              SQLAlchemy models for the backend-owned `tribunal` schema (§6)
    store.py               backend-owned results/history/model-work + concurrency-safe idempotency
  api/
    container.py           dependency wiring (swap reader/provider/external; injects store)
    app.py                 FastAPI routes (contract §2-4), X-Reviewer-Id guard (D-07)
  main.py                  ASGI entrypoint

migrations/                Alembic migration set for the `tribunal` schema (0001_tribunal_schema)
tests/                     §7 flow + failure + integrity suites; fixtures/ (reader, cases, policy)
tools/gen_handoff.py       emits handoff/openapi.json + sample CaseResults
handoff/                   generated artifacts for the lead agent
```

See `ASSUMPTIONS.md` for material assumptions and open questions.
