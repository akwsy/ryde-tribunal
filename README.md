# Ryde Tribunal

Ryde Tribunal is a reviewer workspace for rider and driver disputes. It brings the trip record, evidence, current Ryde policy, both parties’ positions, and the final reviewer decision into one readable case view.

## Try the online demo

Open **[Ryde Tribunal on Vercel](https://ryde-tribunal.vercel.app/)**, then choose **Explore as a reviewer** or **Explore the evidence**. These guest profiles use synthetic examples and are read-only: changes and actions are not saved. Reviewer access that records decisions requires a separate judge passcode; it is not included in this public README.

**Demo status:** the Vercel site is published, but the hosted API currently cannot load the case archive. The Render deployment is blocked by its safety check until both database connection strings point to the dedicated synthetic-only `ryde_tribunal_demo` database. If the page says that the historical archive is unavailable, the backend demo is not ready yet. See [hosted demo setup and status](docs/07-hosted-demo.md).

## What the product does

- Lists and searches current and historical dispute cases.
- Supports intake for eight categories: route deviation, no-show charge, fare calculation, cancellation or waiting fee, property damage, safety incident, lost item, and conduct complaint.
- Collects the relevant trip evidence and policy references, then presents concise rider and driver arguments for review.
- Uses rules-first adjudication for supported routine cases. A Judge can request evidence checks, seek model help for eligible uncertainty, or send a case to a human reviewer.
- Shows the proposed outcome separately from a reviewer’s recorded decision. Financial remedies are recommendations only; the app does not issue refunds, charges, or vouchers.
- Provides read-only historical cases and an activity trace so a reviewer can see what evidence and checks informed the result.

This is a demonstration and review prototype, not connected to Ryde’s production systems. The hosted demo and generated examples use synthetic records with provenance labels. Local deployments can also import records, so operators must follow the data-handling guidance before using non-synthetic data.

## Run locally

Requirements: Python 3.12, Node.js 20 or later, PostgreSQL, and the dependencies listed in the component READMEs. Configure `backend/.env` using [.env.example](.env.example), install dependencies as described in [backend](backend/README.md), [frontend](frontend/README.md), and [database](database/README.md), then run:

```bash
./run-local.sh
```

Open [http://localhost:3000](http://localhost:3000). Local startup uses the configured `ryde_tribunal` database and does not create, reset, or seed it. Keep database credentials and provider keys in ignored local environment files.

## Architecture and technology

The browser application uses Next.js, React, TypeScript, Tailwind CSS, and Recharts. A FastAPI backend handles filing, evidence access, adjudication, policy checks, trace storage, and reviewer actions. PostgreSQL stores trip/evidence data, historical case records, and application state. OpenAPI is the shared API contract at [`shared/openapi.yaml`](shared/openapi.yaml).

The detailed API reference is in [docs/02-api-contract.md](docs/02-api-contract.md). The hosted topology and safe demo setup are in [docs/07-hosted-demo.md](docs/07-hosted-demo.md).

## Development checks

```bash
(cd frontend && npm test && npm run build && npx tsc --noEmit)
(cd backend && uv run pytest -q)
```

PostgreSQL integration tests must use disposable databases ending in `_test` or `_tests`; never run them against the primary local or hosted demo database.
