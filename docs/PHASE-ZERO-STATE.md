# Ryde Tribunal — Project Memory and Phase One Handoff

**Read this first if you are an agent picking up this project.** It is the single source of truth for
what exists, why it is built the way it is, how to run it, and what to do next. It supersedes your
recollection. After this, read `docs/05-integration-log.md` — the running record of every defect this
project has shipped and how each was resolved.

Phase Zero was signed off on 2026-09-25. Phase One is in progress in the current working tree.
Repo: https://github.com/akwsy/ryde-tribunal (private). The validation figures below describe
the Phase Zero baseline; later Phase One validation is recorded in `docs/05-integration-log.md`.

---

## 1. What this project is

Ryde Tribunal adjudicates disputes between ride-hailing riders and drivers. A filed dispute is argued by
a **Rider Advocate** and a **Driver Advocate**, then decided by an impartial **Judge** that applies
versioned policy and issues a ruling with a confidence score. Uncertain, contradictory, insufficient, or
high-impact cases escalate to a human reviewer.

Seed and fixture data are synthetic. The owner may import company-provided trip, profile, and evidence
records into the local test database. Imported rows preserve their source fields and provenance, receive
application-generated internal IDs, and share the same retrieval and adjudication behavior as seeds.
Company exports and personal data must remain outside Git. Dispute filing is separate from data import.

## 2. Phase Zero baseline and current Phase One status

- Three components are integrated in this checkout and run end to end: a filed dispute travels
  database → API → advocates → Judge → frontend and returns a ruling traceable to real ride rows.
- `route_deviation` and `no_show_charge` have automated policy flows. The approved filing vocabulary
  also includes `fare_calculation`, `other_cancellation_fee`, `property_damage`, `safety_incident`,
  `lost_item`, and `conduct_complaint`; categories without automated rules are filed for human review.
- Backend offline suite: 72 passed, 5 PostgreSQL tests skipped when no database DSNs are configured;
  the five live PostgreSQL integration tests separately passed. Database suite: 29 passed against an
  isolated temporary PostgreSQL cluster. Frontend: 157 passed,
  TypeScript check and production build passed. A generated fake CSV import was read by the backend,
  adjudicated, reviewer-approved, and retrieved after rebuilding the app/store.
- One configured Gemini call was attempted against a seeded test case. The call failed and the full
  case completed through `deterministic_mock`; its result was escalated. The project owner confirmed
  this fallback completion counts as Phase Zero evaluation success and signed off Phase Zero on
  2026-09-25. It does not demonstrate case-specific reasoning from a successful live LLM response.
- The current generator targets 100 synthetic users, 160 rides, and 47 archive cases. The
  60-ride/32-archive figures below refer to the signed-off Phase Zero baseline.
- The working tree adds dashboard metrics and review actions, historical read-only case detail,
  simulated filing, ZIP import, evidence audit, fraud assessment, and a safety evidence gate.
  PostgreSQL migration/remap and a successful live-model run remain unverified.

The ZIP-of-CSV importer is documented at `database/importer/FORMAT.md`. It excludes dispute tickets and
cancellation policy; policy remains in the project's existing policy file. Existing company IDs are
skipped without updating stored rows, new rows are appended, and mapping output contains company IDs and
generated internal IDs only. Model-proposed and reviewer-approved rulings are kept separately.
Existing archive history retains its recorded decisions and origin. No model proposal is reconstructed
for old archive cases without an explicit source proposal (open decision D-22).

**Phase One evaluation target — live LLM reasoning remains unverified.** The configured Gemini call failed
before a full LLM case could finish; whole-case deterministic fallback returned a result as required. The
project owner closed D-04 for Phase Zero under the clarified fallback-success criterion. Phase One will
evaluate successful live-model reasoning and any fine-tuned model separately.

**Caveat 2 — `main` is unprotected.** Branch protection is a paid feature on private GitHub repos
(confirmed `403 Upgrade to Pro`). The ownership/one-branch/secret rules are enforced by CI on every PR but
NOT prevented server-side: nothing physically blocks a direct push to `main` or a self-merge. This is open
decision **D-20**. Making the repo public would enable protection for free.

## 3. Repository layout and ownership

| Path | Owner (branch prefix) | Contents |
|---|---|---|
| `database/` | Database specialist (`db/`) | PostgreSQL schema, migrations, synthetic-data generator, read accessors, tests |
| `backend/` | Backend/model specialist (`be/`) | FastAPI service, orchestration, advocates, Judge, policy loader, evidence, persistence |
| `frontend/` | Frontend specialist (`fe/`) | Next.js case-view UI |
| `docs/phase-one/` | Lead agent | Kaggle platform check; training code and benchmark are not yet present |
| `tests/` | QA/integration specialist (`qa/`) | Cross-component acceptance suite |
| `shared/` | Lead agent | `openapi.yaml` — the frozen HTTP contract |
| `docs/` | Lead agent | briefs, contracts, policy, decisions, this file |
| `tools/` | Lead agent | CI guard scripts |

Ownership is ENFORCED, not conventional: `tools/ci/check-ownership.sh` fails any branch whose diff leaves
its owner's tree, and the `lead/` prefix is explicitly forbidden from touching `database/`, `backend/`,
`frontend/`, `tests/`. Full rules in `docs/00-ownership.md` and `docs/06-git-workflow.md`.

## 4. How to run it locally

Prerequisites, all confirmed present on the original dev machine (macOS): PostgreSQL 16 on `:5432`,
Python 3.12 (via `uv`, repo pinned in `.python-version`), Node 20. **No Docker.**

### 4a. Data layer (do this first)
Run each component block from the repository root. These commands describe a fresh database;
an existing database containing archive rows needs the staged `0007` → ID remap → `0008`
procedure in `database/README.md` before the app is started.
```bash
createdb ryde_tribunal                       # safe to skip if it exists
cd database
uv venv --python 3.12.14
export DATABASE_URL="postgresql:///ryde_tribunal"     # SQLAlchemy/Alembic URL, for MIGRATIONS
uv run alembic -c alembic.ini upgrade head            # creates ride_data + case_archive schemas
uv run python -m seed.generator                       # 100 users, 160 rides, 47 archive cases (deterministic)
# To add company trip/profile/evidence rows to this local test database, prepare a ZIP per database/importer/FORMAT.md:
uv run python -m importer validate /path/to/company-export.zip
uv run python -m importer import /path/to/company-export.zip --mapping-out /path/to/company-id-mapping.csv
```
DSN GOTCHA (cost real debugging time): migrations use the SQLAlchemy URL `postgresql+psycopg://...`;
the seed generator and the reader use a PLAIN psycopg DSN `postgresql://...` (no `+psycopg`). They are
NOT interchangeable — the plain form fails Alembic and the SQLAlchemy form fails psycopg with
`missing "=" after ...`. Both are documented in `.env.example`.

### 4b. Backend
```bash
cd backend
cp ../.env.example .env                     # fill local DSNs and optional provider values
uv run alembic upgrade head                  # creates the tribunal schema (backend owns this, separate migration set)
export READ_DATABASE_DSN="postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal"
export TRIBUNAL_DATABASE_DSN="postgresql://APP_WRITER_LOGIN@localhost:5432/ryde_tribunal"
PYTHONPATH=.. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000    # /api/v1/health -> {"database":"ok"}
```
With NO `READ_DATABASE_DSN`, the server wires a `PendingDatabaseReader` that returns
`database_unavailable` on every accessor — correct fail-safe, but it cannot adjudicate. It connects as the
SELECT-only role `ryde_backend_readonly` (the database migration creates it); the backend's own `tribunal`
schema uses a separate writable connection via `TRIBUNAL_DATABASE_DSN`. Two connections, two privilege
levels, by design. The writer login must inherit membership in the NOLOGIN
`ryde_backend_writer` group to allocate shared evidence IDs; it cannot log in as that group.

### 4c. Frontend
```bash
cd frontend
npm install
npm run generate-types                       # regenerates types from ../shared/openapi.yaml — NEVER hand-write them
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1 npm run dev   # http://localhost:3000
```
With NO `NEXT_PUBLIC_API_BASE_URL` the UI runs in fixture mode (no backend). The backend sets CORS headers
for `http://localhost:3000`, so the browser calls `:8000` directly — there is no proxy.

### 4d. Tests
```bash
cd backend  && TRIBUNAL_DATABASE_DSN= READ_DATABASE_DSN= uv run pytest -q  # offline on deterministic_mock
cd database && DATABASE_URL="postgresql:///ryde_tribunal_test" POSTGRES_ADMIN_URL="postgresql:///postgres" uv run pytest -q
cd frontend && npm test                                            # frontend suite
# cross-component + real-Postgres integration:
export RYDE_TEST_READ_DSN="postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal"
cd backend && uv run pytest tests/test_integration_postgres.py -v  # 5, needs seeded Postgres
```
The database suite migrates and seeds the database named by `DATABASE_URL`; it also creates and drops
temporary databases through `POSTGRES_ADMIN_URL`. Point both at a disposable local test PostgreSQL
instance and database. Never point `DATABASE_URL` at the company-data database. Migration rollback tests
use their own temporary database.

### 4e. Useful seeded facts for manual testing
- `RIDE-000001` — 48.3% route deviation, charged BELOW quoted fare → route_deviation rules `no_action`, escalates (confidence 0.68).
- `RIDE-000002` — `cancellation_fee_cents = 0` → `no_show_charge` escalates (contradicted premise, no fee to refund).
- `RIDE-000010`, `RIDE-000030`, `RIDE-000050` — 500-cent cancellation fee → `no_show_charge` refunds S$5.00.

## 5. The integrity rules — the heart of this project

`docs/04-integrity-rules.md` defines rules I-1 through I-8 (plus I-2a) that keep the tribunal from
becoming a scripted demo dressed as an agent. Do NOT weaken these. Every one has an owner and an enforcing
test. The load-bearing ones:

- **I-1** the policy layer returns rule ids + factual measurements ONLY, structurally incapable of
  carrying a verdict; the Judge alone maps measurement+policy→ruling. (`PolicyContext` is frozen and
  validated; `test_i1_red_precomputed_verdict.py` proves the guard fires.)
- **I-2 / I-2a** live ride data has NO outcome fields; historical rows use the same ID formats, and
  archive accessors use their source tables and metadata to avoid reading a live ID as history.
- **I-3** citation validation is semantic (field + value must match the record), not referential.
- **I-5** two different cases must not yield the same argument; **and** the two advocates on one case
  must argue in OPPOSITE directions (`test_adversarial_and_ids.py`). NOTE: the mock provider cannot
  *demonstrate* case-based reasoning (caveat 1) — I-5 is structurally enforced, empirically unproven.
- **I-6** scripted output is labelled `synthetic_reasoning: true` and badged in the UI.
- **I-7** verified evidence outranks unverified on the same fact.

Two hard-won lessons now guarded by regression tests: **a ruling never invents a remedy** — a
refund/compensation must carry a positive amount, and a zero-remedy case escalates rather than refunding
nothing (`test_ruling_integrity.py`, `test_rp_ev003_empty_bundle.py`); and **a "safe" UI fallback that
asserts the worst case is not safe** — absent data must render as unknown, not as invalid.

## 6. Contract discipline (why most bugs happened)

Every defect this project shipped lived BETWEEN components, not inside them, and none was caught by a
component's own tests — each was caught by running the assembled app and looking at it. The pattern: a
contract ambiguous about ownership or meaning produces two defensible readings, and the bug lives where
they meet (`get_case` meaning live-vs-archive; `Citation.valid` defaulted-vs-required; an evidence bundle
specified but assigned to nobody).

Consequences now baked in, do not undo them:
- `shared/openapi.yaml` is the FROZEN contract. It is authored from `docs/02-api-contract.md`, NOT
  generated from the backend. The backend's generated OpenAPI is *diffed against* it at integration; a
  divergence is a defect on one side, never licence to edit one to match the other.
- The read contract has NO write surface. Each component migrates its OWN schema.
- Policy lives in versioned JSON files under `database/seed/policy/`; `ryde-policy-0.1.2.json` is the
  current runtime policy and `ryde-policy-0.1.0.json` and `ryde-policy-0.1.1.json` are preserved for historical records. The version is on
  every ruling. `docs/03-mock-policy.md` is the authoritative prose; the JSON must match it (a test
  enforces this after normalising markdown).

## 7. Phase One — approved scope and delivery order

The project owner signed off Phase Zero on 2026-09-25 and authorized Phase One. Keep these decisions
aligned across the API, backend, database, frontend, and evaluation artifacts.

### 7a. Enhanced judging and evidence

- An evidence-collection model reports advocate claims or evidence that are contradictory, wrong, or
  potentially fabricated. Its findings are shown to and considered by the Judge.
- Fraud risk has greater influence on the Judge's assessment than other non-policy factors, but a fraud
  finding alone never triggers escalation. Make the influence configurable.
- The Judge ranks current policy first and more recent rulings next. Human reviewer-approved rulings have
  higher credibility than model-proposed rulings. Keep these priorities and weights configurable.
- A safety incident with insufficient concrete evidence may be escalated. Any escalation includes a
  concise human-review summary of what evidence does and does not establish.
- Safety cases may be auto-ruled only when all Judge-listed decisive facts resolve to verified evidence,
  no material contradiction/error/fabrication is flagged, and Judge confidence meets the configured threshold.
  Missing or unknown data escalates with a human-review summary.
- Image analysis and image upload are deferred.
- Show which provider produced the result. Keep provider metadata in the result; the UI displays the
  provider name without inventing one when metadata is missing.

### 7b. Reviewer dashboard

- The reviewer is the only intended user. The application stays local and requires no user authentication.
- The dashboard shows filed-case count, confidently judge-resolved count, and human-review escalation
  count for the selected period. All period counts and line-series dates use dispute filing time.
- Date presets are day, week, month, and custom. Dates are inclusive; Singapore time is used; weeks start
  on Sunday. Long custom ranges group relative to the selected range, moving from days to weeks, months,
  and longer intervals as the range grows.
- Show a line graph and pie chart. The pie chart defaults to category; the user can change its grouping
  using a dropdown. Group by category, status, filing party, or provider; exclude review path. Adaptive
  date-bucket cutoffs are configured in `backend/config/dashboard_metrics.json` (daily through 31
  inclusive days, weekly through 365, monthly through 3,650, then yearly). The dashboard defaults to
  Today in Singapore time; other date presets and custom ranges remain available.
- List all cases below the charts, with filtering and sorting by category, status, filing date, and
  urgency. Until a later urgency feature exists, cases default to “not urgent”.
- Include reviewer approval and override flows, retaining proposed and approved rulings separately.

### 7c. Simulated filing and data import

- Add separate pages for simulated dispute filing and company-data import. Keep them out of the main
  dashboard navigation except for small access buttons.
- Simulated filing lets the filer choose rider or driver. Every dispute links to a ride selected from a
  searchable list of database rides using the app's internal ride ID; show the selected ride's details.
- Import a ZIP of related CSV files through the app. Preserve company source IDs and data as specified by
  the importer, generate app-owned internal IDs, and skip records whose company IDs already exist.
- Do not add image upload in this phase.

### 7d. Model platform, dataset, evaluation, and fine-tuning order

1. Set up and check Kaggle first. The local hardware-check notebook is at
   `docs/phase-one/kaggle-platform-check.ipynb`; the account run and actual accelerator output are still
   pending. Do not use the Singapore transport datasets the owner rejected.
2. Define an auditable supervised dataset. Only rulings explicitly approved or overridden by a human
   reviewer may supply training labels. Keep model proposals distinct; exclude unresolved cases and
   deterministic outputs as labels. Do not commit company data or training records to Git.
3. Create a held-out evaluation benchmark authored independently from the policy implementation, with
   boundary coverage and checks through the public API. Record provider, model, fallback occurrence,
   ruling, policy citations, evidence/fraud findings, and human-review outcomes.
4. Establish baseline results before training. Start fine-tuning only after the platform, eligible
   dataset, and benchmark are ready; compare the fine-tuned candidate to that baseline before proposing
   its use by the local application.

## 8. Rules for the next agent (process)

- Work in your OWN clone, never inside another agent's checkout. (This was violated twice and caused an
  unreviewed merge — see integration log PR #5/#6.)
- One branch per specialist prefix at a time; DELETE it after merge or the next PR fails the one-branch
  guard. Merging via `gh pr merge --delete-branch` handles this; a GitHub-UI merge does not.
- Before pushing: `BASE=origin/main bash tools/ci/check-ownership.sh`, `bash tools/ci/check-secrets.sh`,
  `bash tools/ci/check-one-branch.sh`, plus your component's tests. All green.
- Stage explicit paths (`git add database/`), never `git add -A` in a shared checkout.
- The lead agent reviews and merges; specialists do not merge their own PRs.
- When a requirement is ambiguous and the behaviour is material, STOP and ask — do not invent.
- Verify by RUNNING the assembled app, not only by passing component tests. That is where every real bug
  in this project was found.
