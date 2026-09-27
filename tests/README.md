# QA / integration suite

This suite owns cross-component acceptance checks. It drives the public FastAPI HTTP surface and
uses independent in-memory QA records for offline runs; it does not call the orchestrator directly.

## Cold start

From the repository root, install the backend development environment with `cd backend && uv
sync --extra dev`, then run `cd .. && uv run --project backend pytest -q tests` (or activate the
backend environment and run `pytest -q tests`). The deterministic mock provider is the default.

For the seeded integration run, start PostgreSQL 16 with database `ryde_tribunal`, apply both
component migration sets, seed the current 100 users, 160 rides and 47 archive cases, and export
`RYDE_TEST_READ_DSN=postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal`. The QA
fixtures remain the deterministic acceptance baseline; a future live-stack job should additionally
start the backend with `READ_DATABASE_DSN` and exercise the same cases against HTTP.

The prose synchronization check targets current policy version `0.1.2` and validates it against
`docs/03-mock-policy.md`. Historical policy versions `0.1.0` and `0.1.1` remain immutable and are
not expected to match current prose.
