# Backend

FastAPI service for dispute intake, evidence retrieval, adjudication, reviewer actions, and case history.

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
