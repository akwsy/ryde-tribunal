# Ryde Tribunal project guidance

Read [`docs/PHASE-ZERO-STATE.md`](docs/PHASE-ZERO-STATE.md) for the current app and setup, then
check [`docs/05-integration-log.md`](docs/05-integration-log.md) for recent cross-component changes.
The root [`README.md`](README.md) and [`docs/submission/READINESS.md`](docs/submission/READINESS.md)
are the current project overview and release status.

- The local reviewer app and demo use the existing PostgreSQL database `ryde_tribunal`. Do not reset,
  reseed, or run database tests against it. `./run-local.sh` does not migrate or seed data.
- New decisions use `database/seed/policy/ryde-policy-1.1.0.json`. Earlier policy versions remain
  only to explain historical rulings. Keep published Ryde policy distinct from Tribunal operating rules.
- Historical cases are read-only. The archive is generated development data and must not be described
  as real Ryde customer history. Imported and generated records use the same reviewer workflow while
  their provenance remains stored internally.
- Provider proposals, deterministic fallback output, and human decisions remain distinct. Fallback
  is never evidence of successful live-model reasoning. Do not use a ruling or agent transcript as a
  training label without explicit human approval for that individual target.
- `shared/openapi.yaml` is the authoritative API contract. Regenerate frontend types after contract
  changes with `npm run generate-types` in `frontend/`, and record cross-component decisions in the
  integration log.
- PostgreSQL integration tests may create, migrate, seed, and remove only disposable databases whose
  names end in `_test` or `_tests`. Backend unit tests must disable `backend/.env` and use fixtures.
- Keep credentials, company exports, personal data, reviewed labels, generated datasets, and model
  checkpoints outside Git. The local `.env` file is private and ignored.
- Verify the assembled app as well as the affected component. Keep known limitations and measured
  results current in the readiness report; never mark a gate complete without evidence.
