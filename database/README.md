# Ryde Tribunal database layer

Phase Zero database implementation for the database-owned schemas `ride_data` and `case_archive`.

## Guarantees

- Live ride data contains no outcome, verdict, fault, expected-result, resolution, ground-truth, correctness, validity, or refund-granted columns.
- Historical verdicts live only in `case_archive` on disjoint `RIDE-ARCH-*` / `DSP-ARCH-*` identifiers.
- `case_archive` has no foreign keys to `ride_data`.
- The backend role `ryde_backend_readonly` receives `SELECT` on `ride_data` and `case_archive` and no write privileges.
- The reader module exposes exactly eight read accessors and no write surface.

## Setup

From the repository root:

```bash
createdb ryde_tribunal  # safe to skip if it already exists
cd database
uv venv --python 3.12.14
uv pip install -r requirements.lock
```

If your PostgreSQL connection differs from the local default, set:

```bash
export DATABASE_URL="postgresql:///ryde_tribunal"
```

## Migrate

```bash
cd database
uv run alembic -c alembic.ini upgrade head
```

Rollback:

```bash
cd database
uv run alembic -c alembic.ini downgrade base
```

## Seed or reseed

The generator is deterministic. Defaults are `RIDE_DATA_SEED=ride-data-v1` and `CASE_ARCHIVE_SEED=case-archive-v1`.

```bash
cd database
uv run python -m seed.generator
```

Override seeds:

```bash
RIDE_DATA_SEED=my-ride-seed CASE_ARCHIVE_SEED=my-archive-seed uv run python -m seed.generator
```

Generated data includes at least 60 rides and 32 archive cases. Every row has `synthetic = true`.

## Run tests

```bash
cd database
uv run pytest -q
```

The suite covers migration apply/rollback, outcome-freedom, archive/live namespace disjointness, absence of archive-to-live foreign keys, synthetic row counts, referential integrity, route/fare/chat/profile/archive completeness, threshold boundary coverage, seed repeatability, read-accessor validation, and read-only backend-role enforcement.

## Read accessors

Import from `reader`:

```python
from reader import (
    get_case,
    get_chat_log,
    get_fare_breakdown,
    get_gps_samples,
    get_profile,
    get_ride,
    get_route,
    search_archive,
)
```

Examples:

```python
ride = get_ride("RIDE-000001")
route = get_route("RIDE-000001")
gps = get_gps_samples("RIDE-000001")
chat = get_chat_log("RIDE-000001")
fare = get_fare_breakdown("RIDE-000001")
rider = get_profile("USR-R-000001")
archive_case = get_case("DSP-ARCH-000001")
precedents = search_archive("route_deviation", {"category": "route_deviation"}, 5)
```

All return strict Pydantic models. Malformed rows are rejected rather than coerced.

## Backend read-only role

The migration creates `ryde_backend_readonly` with password `ryde_backend_readonly` for local Phase Zero testing. It has `USAGE` and `SELECT` on `ride_data` and `case_archive`, and no `INSERT`, `UPDATE`, or `DELETE`.

For tests that connect as the role:

```bash
export BACKEND_READONLY_DATABASE_URL="postgresql://ryde_backend_readonly:ryde_backend_readonly@localhost:5432/ryde_tribunal"
```
