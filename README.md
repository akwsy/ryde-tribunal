# Ryde Tribunal

Case-specific dispute-resolution system for disputes between Ryde riders and drivers.

Three model components adjudicate a filed dispute: a **Rider Advocate**, a **Driver Advocate**, and an
impartial **Judge** that applies versioned Ryde policy and issues a ruling with a confidence score.
Uncertain, contradictory, insufficient, inaccurate, or high-impact cases escalate to a human reviewer.

Seed and fixture data in Git is synthetic. The owner may import company-provided trip, profile, and
evidence data into the local test database; imported records use the same query and adjudication
behavior as seeded records. Populated company exports and private source data must stay outside Git.

## Status

**Phase One is in progress.** The current work adds reviewer dashboard and actions, historical case
detail, simulated filing, company-data import, and safety evidence checks. The local PostgreSQL
migration, ID remap, and expanded seed were verified on 2026-09-27. Successful live-model reasoning
remains unverified; current validation status is recorded in
[`docs/PHASE-ZERO-STATE.md`](docs/PHASE-ZERO-STATE.md).
- `main` is unprotected: branch protection is a paid feature on private GitHub repos, so the ownership
   and one-branch rules are enforced by CI on every PR but not prevented server-side (decision D-20).

The existing seeded path covers `route_deviation` and `no_show_charge`. Company trip/profile/evidence data
can be imported from a ZIP of related CSVs; disputes are filed separately. Imported source records and
synthetic seeds share the same local query and adjudication path. Categories without implemented policy
rules are filed and sent to human review. Validation counts and safe database test setup are recorded in
[`docs/PHASE-ZERO-STATE.md`](docs/PHASE-ZERO-STATE.md).

**→ New here? Read [`docs/PHASE-ZERO-STATE.md`](docs/PHASE-ZERO-STATE.md) — the full project memory,
run instructions, and Phase One plan. Agents: start at [`AGENTS.md`](AGENTS.md).**

## Quick start

After PostgreSQL has been created, the database migrated and seeded, dependencies installed, and
`backend/.env` configured, start the backend and frontend together from the repository root.
The root `.env.example` is the configuration template: copy it to `backend/.env` and replace
the placeholders locally. The launcher adds the repository root to `PYTHONPATH` for the
database-owned reader and importer modules.

```bash
./run-local.sh
```

Open http://localhost:3000. Press Ctrl+C in the terminal to stop both services. The launcher does not
create or seed the database; the one-time setup steps for a fresh database are below. For an
existing database with archive rows, follow the staged migration and global-ID remap in
`database/README.md` before starting the app.

```bash
# 1. data layer
createdb ryde_tribunal
cd database
uv venv --python 3.12.14
DATABASE_URL="postgresql:///ryde_tribunal" uv run alembic -c alembic.ini upgrade head
uv run python -m seed.generator                       # 100 users, 160 rides, 47 archive cases
# Import company data only after preparing a ZIP per database/importer/FORMAT.md:
uv run python -m importer validate /path/to/company-export.zip
uv run python -m importer import /path/to/company-export.zip --mapping-out /path/to/company-id-mapping.csv

# 2. backend
cd ../backend
cp ../.env.example .env                            # edit local DSNs; never commit .env
uv run alembic upgrade head                          # tribunal schema
READ_DATABASE_DSN="postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal" \
  PYTHONPATH=.. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. frontend
cd ../frontend
npm install && npm run generate-types
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1 npm run dev   # http://localhost:3000
```

Full detail, the DSN gotcha, and seeded test cases are in `docs/PHASE-ZERO-STATE.md` §4.

## Layout and ownership

| Path | Owner | Notes |
|---|---|---|
| `database/` | Database specialist | migrations, seed, tests |
| `backend/` | Backend/model specialist | Python orchestration, advocates, Judge, API |
| `frontend/` | Frontend specialist | Node.js UI |
| `shared/` | Lead agent | approved contracts and schemas only |
| `docs/` | Lead agent | policy, contracts, decisions, historical briefs |
| `tests/` | Lead agent | cross-component acceptance tests |
| `tools/` | Lead agent | CI guard scripts — specialists run them, never edit them |
| `.github/` | Lead agent | CI workflow |

Full rules, including what a specialist may never touch, are in `docs/00-ownership.md`.

## Documents

- `docs/PHASE-ZERO-STATE.md` — **project memory / handoff: state, run instructions, Phase One plan**
- `docs/00-ownership.md` — file boundaries and the integration process
- `docs/01-open-decisions.md` — the owner-decision register (blocking items marked)
- `docs/02-api-contract.md` — HTTP contract between backend and frontend, and the database read contract
- `docs/03-mock-policy.md` — versioned mock Ryde policy, current version `ryde-policy-0.1.2`
- `docs/04-integrity-rules.md` — **non-negotiable** rules that keep this from becoming a scripted demo
- `docs/05-integration-log.md` — every contract change and every defect resolved
- `docs/06-git-workflow.md` — branch model, the one-branch-per-specialist rule, push and PR procedure
- `docs/briefs/` — retained Phase Zero delegation briefs and prompts; current state and runtime
  instructions are in `docs/PHASE-ZERO-STATE.md` and component READMEs

## Git workflow in one line

Each specialist owns a branch prefix (`db/`, `be/`, `fe/`, `qa/`), holds **at most one branch at a
time**, and **pushes to GitHub as soon as its changes are done** — then opens a pull request the lead
agent reviews and squash-merges, after which the branch is deleted to free the slot. The guards in
`tools/ci/` enforce all of it on every pull request. `main` is NOT server-side protected (see Status,
D-20). Details in `docs/06-git-workflow.md`.

## Environment (original dev machine, macOS)

- PostgreSQL 16 on `:5432` — native, no Docker
- Python 3.12 via `uv` (repo pinned in `.python-version`)
- Node 20 for the frontend
