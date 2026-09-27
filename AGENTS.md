# AGENTS.md — start here

You are working on **Ryde Tribunal**, a rider/driver dispute-adjudication system with synthetic test seeds
and support for owner-authorized company data in the local test database.

**Before doing anything, read `docs/PHASE-ZERO-STATE.md` in full.** It is the project's memory: current
state, how to run every component, the integrity rules you must not weaken, the contract discipline that
prevents the class of bug this project kept hitting, and what Phase One is. Then skim
`docs/05-integration-log.md` for the defect history.

Fast facts so you do not guess:
- Seed and fixture data are synthetic. The local test database may also contain company-provided
  records imported by the owner. Imported and synthetic records share the same query and adjudication
  behavior; provenance is retained as data, not used to change rulings.
- Company exports, populated import bundles, real personal data, credentials, and other private source
  records must never be committed to Git. Keep them outside the repository and out of fixtures. Repo is
  private: `akwsy/ryde-tribunal`.
- Phase Zero was signed off by the project owner on 2026-09-25. The configured Gemini request failed and
  deterministic fallback completed the case; per the owner's clarified acceptance, fallback success
  closes D-04 for Phase Zero. Successful live-LLM case-specific reasoning remains a Phase One evaluation
  target. Branch protection remains unavailable on the current GitHub plan (D-20).
- Ownership is enforced by branch prefix and CI guards: `db/`→`database/`, `be/`→`backend/`,
  `fe/`→`frontend/`, `qa/`→`tests/`, `ml/`→`training/`, `lead/`→`shared/ docs/ tools/`. A branch touching another owner's
  tree fails CI. Work in your OWN clone. One branch per prefix; delete it after merge.
- `shared/openapi.yaml` is the authoritative contract; the frontend generates types from it. Cross-component
  changes require a version bump and a `docs/05-integration-log.md` entry. The current policy source
  of truth is `database/seed/policy/ryde-policy-0.1.2.json`; earlier versions are preserved for history.
- The configuration template exists at the repository root as `.env.example`. Copy it to
  `backend/.env` for local runs. `run-local.sh` supplies the monorepo import path.
- Run order: seed the data layer, start the backend with `READ_DATABASE_DSN`, start the frontend with
  `NEXT_PUBLIC_API_BASE_URL`. Exact commands are in `docs/PHASE-ZERO-STATE.md` §4.
- Verify by RUNNING the assembled app. Every real bug here was found that way, not by component tests.
