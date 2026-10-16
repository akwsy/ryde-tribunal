# Backend

FastAPI service for the Ryde Tribunal dispute-review product: it handles dispute intake, trip and evidence retrieval, policy checks, adjudication, case history, and reviewer decisions. The product overview and local startup steps are in the [root README](../README.md). The online demo is [ryde-tribunal.vercel.app](https://ryde-tribunal.vercel.app/); its frontend is live, but case data depends on the Render API and the dedicated Neon demo database. See [hosted demo status and setup](../docs/07-hosted-demo.md).

## Setup

Use Python 3.12 and `uv`:

```bash
uv sync --extra dev
```

Copy the root [.env.example](../.env.example) to `backend/.env` and configure local database connections. Keep credentials out of Git. The root [README](../README.md) describes the normal app startup; database setup and migrations are documented in [database/README.md](../database/README.md).

## Run the API alone

```bash
PYTHONPATH=.. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Interactive API documentation is available at `http://localhost:8000/docs`.

## Tests

```bash
uv run pytest -q
```

Tests default to the deterministic offline provider. PostgreSQL integration tests require a disposable database ending in `_test` or `_tests`; never use the persistent application database for tests.
