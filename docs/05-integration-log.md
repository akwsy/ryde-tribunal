# 05 — Integration log

Every change to `shared/` and every cross-component decision is recorded here by the lead agent. A
specialist requests an entry; it never writes one.

Format:

```
## YYYY-MM-DD — <short title>
- Requested by: <specialist>
- Reason:
- Components affected:
- Contract change: <none | shared/openapi.yaml v0.1.0 -> v0.1.1 | ...>
- Decision:
- Tests updated:
```

## 2026-09-22 — Repository and contract baseline
- Requested by: lead agent
- Reason: Phase Zero foundation — ownership boundaries, contracts, policy, integrity rules, briefs.
- Components affected: all.
- Contract change: `docs/02-api-contract.md` draft v0.1.0 authored. `shared/openapi.yaml` **not yet
  generated** — it is frozen from this document once the open decisions in `docs/01-open-decisions.md`
  are approved.
- Decision: no specialist is dispatched until the blocking decisions D-01, D-02, D-03, D-04, D-07 and
  D-12 are resolved by the project owner.
- Tests updated: none yet; `tests/` cross-component suite is authored after the gate clears.

## 2026-09-22 — Git workflow: push-when-done, one branch per specialist
- Requested by: project owner.
- Reason: owner rule — every specialist pushes to GitHub whenever its changes are done, and each may hold
  at most one branch at a time.
- Components affected: all three specialists, plus new lead-owned `tools/ci/` and `.github/`.
- Contract change: none to `shared/`. New `docs/06-git-workflow.md`; a §10 "Git and GitHub" section added
  to all three briefs; `docs/00-ownership.md` gains `tools/` and `.github/` and a new §6 on enforcement.
- Decision: the rule is enforced mechanically rather than by instruction. Each specialist owns a branch
  prefix (`db/`, `be/`, `fe/`, `lead/`); `tools/ci/check-one-branch.sh` fails when a prefix holds more
  than one remote branch or when a branch has no recognized prefix;
  `tools/ci/check-ownership.sh` fails a branch whose diff leaves its owner's tree;
  `tools/ci/check-secrets.sh` scans changed files for credential and real-personal-data patterns. All
  three run in `.github/workflows/guards.yml` on every pull request. Merges are squash merges so one
  branch becomes one attributable commit. Specialists do not merge their own pull requests.
- Consequence: a GitHub remote and branch protection are now **blocking** for all three specialists —
  recorded as D-19 and D-20. A specialist cannot satisfy "push when done" with no remote.
- Tests updated: three guard scripts added; syntax-checked and dry-run locally. They exercise for real on
  the first pull request, since `check-one-branch.sh` requires a remote.

## 2026-09-22 — Contract defect: `persist_model_work` removed from the read contract
- Requested by: database specialist (raised before writing code, correctly).
- Reason: the specialist found a genuine contradiction in contract draft v0.1.0. `docs/02-api-contract.md`
  §5 is headed "Database read contract" yet listed `persist_model_work(case_id, payload)`, a write. §6
  assigned `model_work_*` to the backend, and the database brief §2 forbade the database specialist from
  creating those tables. So the accessor could not be implemented by its stated owner.
- Components affected: database and backend.
- Contract change: `docs/02-api-contract.md` §5 — `persist_model_work` **removed**; the read contract is
  now **eight accessors and has no write surface at all**. §5 gains a schema-ownership table and §6 is
  rewritten so each component migrates its own schema.
- Decision: the read contract is read-only by construction, which is the stronger reading of integrity
  rule I-2 — the data the tribunal reasons over cannot be mutated by the reasoner. Ownership moves from
  convention to PostgreSQL grants: `ride_data` and `case_archive` belong to the database specialist and
  the backend role holds `SELECT` only; `tribunal` belongs to the backend, which migrates it with its own
  migration set under `backend/` and persists advocate and Judge work itself. `ingest_audit` is the
  generator's own provenance record and is explicitly not a landing zone for model output.
- Consequence: the database specialist delivers 8 accessors, not 9, plus a restricted backend role, plus a
  test proving `INSERT` is refused. The backend gains its own migration set — a scope increase it must be
  told about, since it was originally told it writes no migrations at all.
- Tests updated: database brief §7 gains a no-write-surface test; backend brief §2 and §5 corrected.

## 2026-09-22 — Near-miss: `get_case` meant two different things
- Requested by: lead agent, on reviewing PR #3 and PR #4 together, prompted by the backend's open
  question A-9.
- Reason: the contract's `get_case(case_id)` was implemented by the database specialist as
  `get_case(case_id) -> ArchiveCase` (an archived case) while the backend expected the live dispute under
  adjudication. Both readings are defensible against the original wording, which said only "dispute header
  and evidence references".
- Severity: this is the dangerous class, not the untidy class. Had both sides shipped and integrated, the
  backend would have fetched an **outcome-bearing archive record for the case it was adjudicating** — the
  "case looks up its own answer" failure that integrity rule I-2 exists to prevent, arriving through an
  ambiguous function name rather than a bad column. Neither component was wrong on its own terms, and
  neither component's own tests could have caught it.
- Components affected: database and backend.
- Contract change: `get_case` **removed** from `docs/02-api-contract.md` §5. The read contract is now
  **seven ride/user accessors plus two explicitly archive-namespaced ones** (`search_archive`,
  `get_archive_case`). §6 states that the live case is the backend's end to end.
- Decision: the live case lives in `tribunal.case_*`, written by `POST /disputes` and read back by the
  backend from its own schema — there is no accessor for it. An evidence bundle is assembled at
  adjudication time from `ride_data` reads plus party submissions in `tribunal`. Archive access is renamed
  to `get_archive_case` and must **raise** on a live `DSP-*` id rather than return anything. This also
  answers the backend's A-9: filing persists the dispute; nothing joins a live case to `case_archive`.
- New rule: `docs/04-integrity-rules.md` gains **I-2a** — every archive accessor validates an
  archive-namespaced id and raises on a live one.
- Tests updated: I-2a requires `get_archive_case("DSP-000045")` to raise and
  `get_archive_case("DSP-ARCH-000017")` to succeed. Both PRs need a revision before merge.
