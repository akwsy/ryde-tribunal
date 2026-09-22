# Ryde Tribunal

Case-specific dispute-resolution system for disputes between Ryde riders and drivers.

Three model components adjudicate a filed dispute: a **Rider Advocate**, a **Driver Advocate**, and an
impartial **Judge** that applies versioned Ryde policy and issues a ruling with a confidence score.
Uncertain, contradictory, insufficient, inaccurate, or high-impact cases escalate to a human reviewer.

**All data in this repository is synthetic.** No real riders, drivers, rides, payments, or personal data.

## Status

Phase Zero — **not started**. Awaiting project-owner approval of the open decisions in
`docs/01-open-decisions.md`. No specialist implementation begins before that gate clears.

## Layout and ownership

| Path | Owner | Notes |
|---|---|---|
| `database/` | Database specialist | migrations, seed, tests |
| `backend/` | Backend/model specialist | Python orchestration, advocates, Judge, API |
| `frontend/` | Frontend specialist | Node.js UI |
| `shared/` | Lead agent | approved contracts and schemas only |
| `docs/` | Lead agent | briefs, policy, contracts, decisions |
| `tests/` | Lead agent | cross-component acceptance tests |
| `tools/` | Lead agent | CI guard scripts — specialists run them, never edit them |
| `.github/` | Lead agent | CI workflow |

Full rules, including what a specialist may never touch, are in `docs/00-ownership.md`.

## Documents

- `docs/00-ownership.md` — file boundaries and the integration process
- `docs/01-open-decisions.md` — the owner-decision register (blocking items marked)
- `docs/02-api-contract.md` — HTTP contract between backend and frontend, and the database read contract
- `docs/03-mock-policy.md` — versioned mock Ryde policy, `ryde-policy-0.1.0`
- `docs/04-integrity-rules.md` — **non-negotiable** rules that keep this from becoming a scripted demo
- `docs/05-integration-log.md` — every change to a shared contract
- `docs/06-git-workflow.md` — branch model, the one-branch-per-specialist rule, push and PR procedure
- `docs/briefs/` — one brief per specialist

## Git workflow in one line

Each specialist owns a branch prefix (`db/`, `be/`, `fe/`), holds **at most one branch at a time**, and
**pushes to GitHub as soon as its changes are done** — then opens a pull request the lead agent reviews
and squash-merges, after which the branch is deleted to free the slot. `main` is protected. The guards in
`tools/ci/` enforce all of it on every pull request. Details in `docs/06-git-workflow.md`.

## Local environment as measured on this machine

- PostgreSQL 16.15 (Homebrew), running, accepting connections on `:5432`
- Python 3.14.7, `uv` available
- Docker: **not installed** — Postgres runs natively, no compose file
- Node.js / npm: **not installed** — blocks the frontend specialist, see decision `D-12`
