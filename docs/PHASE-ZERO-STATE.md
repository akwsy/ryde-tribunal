# Ryde Tribunal — Project Memory & Handoff (Phase Zero → Phase One)

**Read this first if you are an agent picking up this project.** It is the single source of truth for
what exists, why it is built the way it is, how to run it, and what to do next. It supersedes your
recollection. After this, read `docs/05-integration-log.md` — the running record of every defect this
project has shipped and how each was resolved.

Last updated: 2026-09-23, end of Phase Zero. Repo: https://github.com/akwsy/ryde-tribunal (private).

---

## 1. What this project is

Ryde Tribunal adjudicates disputes between ride-hailing riders and drivers. A filed dispute is argued by
a **Rider Advocate** and a **Driver Advocate**, then decided by an impartial **Judge** that applies
versioned policy and issues a ruling with a confidence score. Uncertain, contradictory, insufficient, or
high-impact cases escalate to a human reviewer.

**All data is synthetic.** No real riders, drivers, rides, payments, or personal data. This is a demo /
prototype, not a production system.

## 2. Current state (Phase Zero — functionally complete, two caveats)

- Three components integrated on `main` and running end to end: a filed dispute travels
  database → API → advocates → Judge → frontend and returns a ruling traceable to real ride rows.
- Two categories adjudicate end to end: `route_deviation` and `no_show`. (`property_damage` and
  `safety_incident` are schema-supported but not adjudicated — Phase One.)
- Tests: backend 70, database 17, frontend 145, cross-component suite in `tests/`.
- Data layer seeded: 60 synthetic rides, 32 archive cases.

**Caveat 1 — the central requirement is NOT demonstrated.** Everything runs on the `deterministic_mock`
model provider, which composes argument text from templates. The mission requires that conclusions derive
from the *case*, not a template. That is enforced *structurally* (see §5) but has never been run against a
real LLM. Until `MODEL_PROVIDER=openai_compatible` is exercised with real credentials, "reasoning from the
case" is guaranteed by construction, not shown empirically. This is open decision **D-04**.

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
```bash
createdb ryde_tribunal                       # safe to skip if it exists
cd database
uv venv --python 3.12.14
export DATABASE_URL="postgresql:///ryde_tribunal"     # SQLAlchemy/Alembic URL, for MIGRATIONS
uv run alembic -c alembic.ini upgrade head            # creates ride_data + case_archive schemas
uv run python -m seed.generator                       # 60 rides, 32 archive cases (deterministic)
```
DSN GOTCHA (cost real debugging time): migrations use the SQLAlchemy URL `postgresql+psycopg://...`;
the seed generator and the reader use a PLAIN psycopg DSN `postgresql://...` (no `+psycopg`). They are
NOT interchangeable — the plain form fails Alembic and the SQLAlchemy form fails psycopg with
`missing "=" after ...`. Both are documented in `.env.example`.

### 4b. Backend
```bash
cd backend
uv run alembic upgrade head                  # creates the tribunal schema (backend owns this, separate migration set)
export READ_DATABASE_DSN="postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000    # /health -> {"database":"ok"}
```
With NO `READ_DATABASE_DSN`, the server wires a `PendingDatabaseReader` that returns
`database_unavailable` on every accessor — correct fail-safe, but it cannot adjudicate. It connects as the
SELECT-only role `ryde_backend_readonly` (the database migration creates it); the backend's own `tribunal`
schema uses a separate writable connection via `TRIBUNAL_DATABASE_DSN`. Two connections, two privilege
levels, by design.

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
cd backend  && uv run pytest -q                                    # 70, offline on deterministic_mock
cd database && uv run pytest -q                                    # 17
cd frontend && npm test                                            # 145
# cross-component + real-Postgres integration:
export RYDE_TEST_READ_DSN="postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal"
cd backend && uv run pytest tests/test_integration_postgres.py -v  # 5, needs seeded Postgres
```

### 4e. Useful seeded facts for manual testing
- `RIDE-000001` — 48.3% route deviation, charged BELOW quoted fare → route_deviation rules `no_action`, escalates (confidence 0.68).
- `RIDE-000002` — `cancellation_fee_cents = 0` → no_show escalates (contradicted premise, no fee to refund).
- `RIDE-000010`, `RIDE-000030`, `RIDE-000050` — 500-cent cancellation fee → no_show refunds S$5.00.

## 5. The integrity rules — the heart of this project

`docs/04-integrity-rules.md` defines rules I-1 through I-8 (plus I-2a) that keep the tribunal from
becoming a scripted demo dressed as an agent. Do NOT weaken these. Every one has an owner and an enforcing
test. The load-bearing ones:

- **I-1** the policy layer returns rule ids + factual measurements ONLY, structurally incapable of
  carrying a verdict; the Judge alone maps measurement+policy→ruling. (`PolicyContext` is frozen and
  validated; `test_i1_red_precomputed_verdict.py` proves the guard fires.)
- **I-2 / I-2a** live ride data has NO outcome fields; the archive is a disjoint id namespace
  (`RIDE-ARCH-*`, `DSP-ARCH-*`) an archive accessor RAISES on a live id.
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
- Policy lives in ONE file: `database/seed/policy/ryde-policy-0.1.0.json`, loaded at runtime, version on
  every ruling. `docs/03-mock-policy.md` is the authoritative prose; the JSON must match it (a test
  enforces this after normalising markdown).

## 7. What to do next (Phase One) — DO NOT START until Phase Zero is signed off

From the handoff §3/§5, in rough priority:
1. **Demonstrate the central requirement (closes caveat 1).** Wire real `openai_compatible` credentials,
   run the eval corpus against a real model, confirm arguments genuinely vary by case. This is the single
   most valuable unproven thing.
2. **Enhanced Judge**: evidence-collection sub-model, fraud/bad-faith detection, policy+precedent RAG.
3. **Dispute-manager dashboard** (~80% feature-complete): today/week/month counts, auto-vs-human time
   series, human-review queue with urgency sort, approve/override flows. Contract endpoints already exist
   (`/metrics/*`), the frontend renders only the case view so far.
4. Adjudicate `property_damage` and `safety_incident` end to end.
5. Real auth (Phase Zero uses a single `X-Reviewer-Id` header, D-07).

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
