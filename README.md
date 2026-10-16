# Ryde Tribunal

Ryde Tribunal is a local workspace for reviewing rider and driver disputes. It brings trip records, supporting evidence, Ryde policy, and reviewer decisions together in one case view.

## Run locally

The app uses a local PostgreSQL database and requires Python 3.12 and Node.js. Configure `backend/.env` from [.env.example](.env.example), install the backend and frontend dependencies using their component READMEs, then start the app:

```bash
./run-local.sh
```

Open [http://localhost:3000](http://localhost:3000). The launcher connects to the configured `ryde_tribunal` database. It does not create, reset, or seed a database. Keep database credentials and provider keys in the ignored local environment file.

## Hosted judge demo

The project includes an isolated, synthetic-only hosted demo with read-only guest profiles and passcode-protected reviewer access. Guest changes are not saved; reviewer actions are recorded in the demo database. See [hosted demo setup](docs/07-hosted-demo.md) for the one-time Neon setup and Vercel/Render configuration.

## What it does

- Lists current and historical disputes with search, filters, and case details.
- Processes all eight filing categories. Supported routine fare and fee cases can be resolved by rules; other cases receive evidence triage and human review when required.
- Shows the rider and driver submissions, evidence sources, policy references, processing trace, and reviewer decision.
- Uses configured AI review only when the rules-first Judge remains uncertain. Provider output is checked before use; failures are sent for human review.
- Keeps financial outcomes as recommendations. It does not issue refunds, charges, or vouchers.

## Stack

Next.js, React, TypeScript, Tailwind CSS, FastAPI, Pydantic, PostgreSQL, SQLAlchemy, Alembic, and OpenAPI. The machine-readable API contract is in [`shared/openapi.yaml`](shared/openapi.yaml); the [API reference](docs/02-api-contract.md) explains the case and evidence flows.

## Data and scope

Historical sample records may be generated for development and evaluation; their provenance is retained in the application. They are not real Ryde customer records. The app is a local prototype and does not connect to Ryde’s production systems or execute financial actions.
