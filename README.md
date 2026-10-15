# Ryde Tribunal

Ryde Tribunal helps local reviewers assess rider and driver disputes using evidence, versioned Ryde policy, and three role-based agents: Rider Advocate, Driver Advocate, and Judge. Uncertain cases go to human review. Financial outcomes are recommendations only.

## Run the app

The normal app and demonstration use the same local PostgreSQL database, `ryde_tribunal`. The existing database contains historical dispute decisions and current filings; startup does not create, reset, or reseed it.

1. Make sure PostgreSQL is running and `backend/.env` has valid local database and provider settings. The checked-in `.env.example` documents the required variables; keep credentials in the ignored local file.
2. From the repository root, start both services:

   ```bash
   ./run-local.sh
   ```

3. Open [http://localhost:3000](http://localhost:3000). The case list shows all filing dates; dashboard charts use the selected date period.

The root launcher stops both services with Ctrl+C. For a new machine, install the Python and Node dependencies and apply forward migrations using the steps in [database setup](database/README.md) and [backend setup](backend/README.md). Do not run the seed generator against a database that contains records you need to preserve.

## What is included

- A Next.js reviewer workspace for all live and historical cases, with search, filters, and pagination.
- All eight filing categories enter automated processing. Route, no-show, fare, and supported rider-fee cases use rules-first adjudication and selective model review; damage, safety, lost-item, and conduct cases receive evidence triage and require a human final decision.
- A case view that puts the outcome first and opens readable evidence cards into a draggable source viewer. GPS records show available trip points on an OpenStreetMap-backed map; missing or offline map data has a text fallback.
- Filing accepts up to five PDF, JPEG, or PNG supporting files (4 MB each, 8 MB total). Party uploads are marked unverified, remain separate from verified trip records, and can be opened by reviewers from the evidence list.
- PostgreSQL storage for trip records, historical rulings, current cases, and reviewer decisions.
- Source-backed policy 1.1.0 for new cases, including fare, cancellation-fee, damage, safety, lost-item and conduct guidance. Older decisions retain the policy version under which they were recorded.

The historical seed corpus is generated for development and evaluation, not a set of real Ryde customer cases. Record provenance stays in the database and project documentation. Imported records use the same app paths and adjudication behavior.

## Technology

- Frontend: Next.js, React, TypeScript, Tailwind CSS, Recharts, Leaflet.
- API: Python, FastAPI, Pydantic, OpenAPI, and `openapi-fetch` client calls.
- Data: PostgreSQL, SQLAlchemy/Alembic, and a read-only ride-data adapter.

## Project status

This is a local MVP preview. Two synthetic route and no-show cases now complete with `gemini-3.1-flash-lite` without fallback. The full independent benchmark, persistent live trace check, demo recording, and genuine CodeBuddy/WorkBuddy screenshots remain outstanding. See [current readiness](docs/submission/READINESS.md).

## Project guidance

- [Project state and run instructions](docs/PHASE-ZERO-STATE.md)
- [API contract](docs/02-api-contract.md) and [OpenAPI schema](shared/openapi.yaml)
- [Integrity rules](docs/04-integrity-rules.md)
- [Current source-backed policy](database/seed/policy/ryde-policy-1.1.0.json)
- [Submission readiness](docs/submission/READINESS.md)
- [Architecture and demo script](docs/submission/architecture.svg) · [demo script](docs/submission/DEMO-SCRIPT.md)

The GitHub repository remains private. Company exports, personal records, credentials, review labels, and training checkpoints stay outside Git.
