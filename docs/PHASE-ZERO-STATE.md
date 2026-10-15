# MVP setup and current state

The root [README](../README.md) is the public-facing project overview. This file keeps the
operational setup and current verification notes for the local reviewer MVP.

## Local startup

The normal app uses the existing `ryde_tribunal` PostgreSQL database. `./run-local.sh` starts
FastAPI on port 8000 and Next.js on port 3000, checks database health, and stops both services
when you press Ctrl+C. Startup does not migrate, reset, reseed, or import data.

Configure `backend/.env` from the root `.env.example`. Keep the read-only ride/archive DSN and
tribunal writer DSN pointed at the same local database, select policy `ryde-policy-1.1.0` for new
cases, and provide model settings if you want to test the live provider. Keep credentials in the
ignored local file. Install dependencies with `uv sync --extra dev` in `backend/` and `npm install`
in `frontend/`.

The current local database has 47 historical archive decisions and one current filing. Archived
decisions retain their original policy version and are read-only. New filings and historical
records share the same list and detail experience. The generated archive is synthetic development
data; it is not represented as real Ryde customer history.

## Components

| Directory | Responsibility |
| --- | --- |
| `frontend/` | Reviewer dashboard, dispute filing, evidence viewer and maps |
| `backend/` | FastAPI contract, evidence tools, policy checks, agent workflow and persistence |
| `database/` | PostgreSQL migrations, trip/archive data, read accessors and policy snapshots |
| `shared/openapi.yaml` | Authoritative API contract; frontend types are generated from it |
| `training/` | Reproducible synthetic corpus and approval-gated training workflow |
| `docs/submission/` | Architecture, demo script, project description, cover images and readiness checklist |

The UI calls documented endpoints through the generated OpenAPI client. The backend reads trip
and archive data through the read-only adapter and stores current filings, traces, and reviewer
decisions in the `tribunal` schema. Financial outcomes are recommendations; the app does not execute
payments.

## Verification

Run frontend tests and production build from `frontend/`:

```bash
npm test
npm run build
npx tsc --noEmit
```

Run backend unit tests from `backend/`:

```bash
.venv/bin/python -m pytest -q
```

Run database PostgreSQL acceptance tests only against a disposable database whose name ends in
`_test` or `_tests`; they may create, migrate, seed, and drop that test database. Never point
database tests at `ryde_tribunal`.

## Current readiness

On 13 October 2026, the local list API returned 48 records. The dashboard rendered at 390, 768,
and 1440 pixel widths without horizontal overflow. Backend, database, and frontend unit/build
checks pass. Live-provider adjudication for both core categories, an independent benchmark, and
the final recorded demo remain outstanding; see [submission readiness](submission/READINESS.md).
