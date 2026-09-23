# AGENTS.md — start here

You are working on **Ryde Tribunal**, a synthetic rider/driver dispute-adjudication system.

**Before doing anything, read `docs/PHASE-ZERO-STATE.md` in full.** It is the project's memory: current
state, how to run every component, the integrity rules you must not weaken, the contract discipline that
prevents the class of bug this project kept hitting, and what Phase One is. Then skim
`docs/05-integration-log.md` for the defect history.

Fast facts so you do not guess:
- All data is SYNTHETIC. Repo is private: `akwsy/ryde-tribunal`.
- Phase Zero is functionally complete with two caveats: the "reasoning from the case" requirement is
  structurally enforced but never run against a real LLM (deferred, decision D-04), and `main` is
  unprotected because branch protection is Pro-gated on a private repo (decision D-20).
- Ownership is enforced by branch prefix and CI guards: `db/`→`database/`, `be/`→`backend/`,
  `fe/`→`frontend/`, `qa/`→`tests/`, `lead/`→`shared/ docs/ tools/`. A branch touching another owner's
  tree fails CI. Work in your OWN clone. One branch per prefix; delete it after merge.
- `shared/openapi.yaml` is the frozen contract; the frontend generates types from it. The single policy
  source of truth is `database/seed/policy/ryde-policy-0.1.0.json`.
- Run order: seed the data layer, start the backend with `READ_DATABASE_DSN`, start the frontend with
  `NEXT_PUBLIC_API_BASE_URL`. Exact commands are in `docs/PHASE-ZERO-STATE.md` §4.
- Verify by RUNNING the assembled app. Every real bug here was found that way, not by component tests.
