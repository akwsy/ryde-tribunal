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

## 2026-09-22 — `shared/openapi.yaml` published at v0.1.0
- Requested by: frontend specialist (blocked on a type-generation source that did not exist).
- Reason: the frontend brief required generating types from `shared/openapi.yaml`, which had never been
  authored. The specialist proposed authoring a local copy at `frontend/openapi.yaml` instead.
- Components affected: frontend (unblocked), backend (integration diff target).
- Contract change: `shared/openapi.yaml` created — OpenAPI 3.1.0, 11 paths, 12 operations, 32 schemas,
  all `$ref`s resolved, every operation carrying an `operationId`. `docs/02-api-contract.md` §1 gains an
  authoritative display-rules subsection.
- Decision: the local-copy proposal was **refused**. Duplicating the API surface into `frontend/` repeats
  the mistake D-18 exists to prevent — two copies that drift, with the divergence invisible until
  integration. Authoring `shared/` is the lead agent's job and it is now done.
  Direction matters and is stated in the file: this spec was authored from the prose contract, NOT
  generated from the backend's implementation. The backend's own `backend/handoff/openapi.json` is
  **diffed against** it at integration, and a divergence is a defect on one side, never licence to edit
  one to match the other.
  Display decisions: money renders via `Intl.NumberFormat('en-SG', …)` as `S$3.25` — the handoff's bare
  `$3.25` was prose shorthand; confidence renders as a percentage to one decimal with the raw float in a
  tooltip. The client must branch on `judge.escalation.escalated`, never on a threshold comparison,
  because `0.6996` displays as `70.0%` and would appear to clear a bar it did not clear.
- Tests updated: none yet. `shared/openapi.yaml` is frozen at v0.1.0 for Phase Zero; a change requires a
  new entry here and a version bump.

## 2026-09-22 — First run of the assembled stack: two integration gaps
- Requested by: lead agent, on attempting to actually run the merged components end to end.
- Reason: all three components were merged and each passed its own suite (backend 46, database 16,
  frontend 145). Nothing had ever been started together.
- Findings:
  1. **Policy field-name mismatch — backend defect, server will not start.** The canonical policy file
     `database/seed/policy/ryde-policy-0.1.0.json` (the D-18 single source of truth) uses
     `rules[].id`; `shared/openapi.yaml` `PolicyDocument` requires `[id, text]`; but
     `backend/app/policy/context.py:41` declares `rule_id`. Pointed at the real file the backend dies at
     startup with 28 Pydantic `rule_id Field required` errors. The database side matches the contract, so
     this is the backend's to fix.
     The backend *predicted* this in its own assumption A-1 — it loaded a transcribed fixture and said it
     should be diffed against the seed at integration. It was right, and neither component's own suite
     could have caught it: each was internally consistent.
  2. **No Postgres reader adapter exists.** `backend/app/main.py` wires a `PendingDatabaseReader` that
     raises `DatabaseUnavailable` on every accessor, so a served request returns `database_unavailable`
     and never a fabricated ruling — correct behaviour, but it means the stack cannot run end to end.
     The seam is `app.api.container.build_container(reader=…)`.
- Ownership note: the integration adapter must be written by the **backend specialist**, not the lead
  agent. `tools/ci/check-ownership.sh` now forbids a `lead/` branch from touching `backend/` (added in
  PR #7 after the PR #5 incident), so the lead agent is correctly unable to do this work itself. That is
  the guard functioning as designed, not an obstacle to route around.
- Also observed: the data layer is migrated and seeded with 60 rides and 32 archive cases (above the
  50/30 minimums), and the seed generator wants a plain psycopg DSN rather than the
  `postgresql+psycopg://` SQLAlchemy URL shown in `.env.example` — worth a documentation fix.

## 2026-09-22 — First LOOK at the running UI: two defects no test could catch
- Requested by: lead agent, reviewing PR #18 (frontend live integration) by opening the screenshots.
- Context: PR #17 (full policy prose restored, markdown sync test) and PR #18 (live integration against
  the real backend, 6 screenshots, contract defect report) are both merged. The frontend had until now
  only ever run against fixtures, and no human or agent had looked at the rendered UI.
- Findings from the screenshot, neither visible to any existing suite:
  1. **Every citation renders `(invalid)` — 10 of 10, in red.** The backend omits the `valid` field that
     `shared/openapi.yaml` declares with `default: true`, and the frontend's fallback treats absent as
     invalid. So a case whose validation passed cleanly (`invalid_citation_count: 0`) is presented to a
     reviewer as one where no cited evidence supports any claim. Two defects compounding: the backend
     omits a defaulted field, and the frontend's "safe" fallback chose the most alarming reading of
     missing data rather than an unknown state.
  2. **The Driver Advocate argues the rider's case.** Its claims 1 and 2 read "the route ran far beyond
     any reasonable tolerance" and "the extra distance represents an extreme excess over what was
     quoted" — word-identical to the Rider Advocate's. The driver's own advocate concedes the
     overcharge. This is integrity rule I-5's concern made concrete: both advocates share a generated
     preamble, so the adversarial framing collapses. The structural I-5 test cannot see it, because the
     two advocates DO cite different evidence sets; only the prose is shared.
- Also: booleans with falsey values (`deviation_justified`, `filing_asserts_fee`) render as blank rather
  than "No".
- On the frontend's own defect report: items 1, 2, 3 and 5 are confirmed. **Item 4 is incorrect** —
  `subject` IS documented in `FileDisputeRequest` and is in its `required` list. Reported here so the
  correction is on record rather than propagating.
- The CORS workaround (a Next.js rewrites proxy) is accepted for Phase Zero but is a workaround: the
  backend should set CORS headers for the dev origin, and the proxy should then be removed.

## 2026-09-22 — Two contract rulings on the UI defects
- Requested by: lead agent, resolving the items the frontend's live-integration report raised.
- Ruling 1 — **`Citation.valid` is now REQUIRED, not defaulted.** It was declared `default: true`, which
  the backend read as omittable and the frontend then had to interpret; the frontend chose "absent means
  invalid", so a cleanly-validated case rendered with all ten citations marked invalid in red. A default
  is a statement about what a value MEANS when absent, and two components inferred opposite meanings from
  it. Absence is now a schema violation, so neither side has to guess.
- Ruling 2 — **`invalid_citation_rate` is added to the contract**, on `AdvocateOutput`. The backend was
  already sending it and the metric is genuinely useful, so the contract was wrong to omit it rather than
  the backend wrong to send it. Its description states explicitly that it is an invalid-CITATION rate and
  not an unsupported-claim rate, because that exact mislabelling is called out in integrity rule I-3.
- Ruling 3 — **the backend conforms to `^EV-\d{6}$`; the pattern is NOT widened.** The frontend reported
  ids shaped `EV-000123-1`. Widening the pattern to accept a suffix would leave two id shapes in one
  system, in URLs, in citations, and in the frontend's generated types. The backend owns the case and its
  evidence, so it can allocate a per-case sequence. One shape.
- Not ruled, deliberately: the **Driver Advocate sharing the Rider Advocate's prose** is a backend
  reasoning defect, not a contract question. No schema change can fix an advocate that concedes its own
  party's case.

## 2026-09-24 — Company data import and persistent adjudication contract
- Requested by: project owner.
- Reason: Phase Zero cleanup must support importing company trip/profile/evidence records, querying them
  during a separately filed dispute, and retaining both model and reviewer decisions.
- Components affected: database, backend, frontend, shared contract, project documentation.
- Contract change: `docs/02-api-contract.md` and `shared/openapi.yaml` v0.1.0 -> v0.1.1.
- Decision: provide a ZIP of related CSVs through the database CLI; app-generated internal IDs are mapped
  separately from retained company IDs. Duplicate company IDs are detected globally by entity type,
  skipped without update, and existing internal user IDs are reused when a new trip links to that user.
  `no_show_charge` replaces `no_show`; all eight approved categories can be filed, while categories
  without automated rules are retained and routed to human review without a model ruling. Imported and
  synthetic rows share the same query/adjudication path; provenance is metadata. Cancellation policy
  stays in the existing project policy file. A model proposal and a human-approved/overridden ruling are
  distinct records, with human origin marked at higher credibility. The read contract adds the ninth
  accessor `get_app_events(ride_id)`.
- Tests updated: backend suite 71 passed / 5 PostgreSQL tests skipped with DB DSNs blank; frontend and DB
  tests are being run separately. Full Postgres integration has not yet been validated.

## 2026-09-25 — Phase Zero integration validation and safe rollback checks
- Requested by: project owner.
- Components checked: database, backend, frontend, shared API contract, and imported-record flow.
- Contract/runtime validation: backend offline suite 72 passed / 5 live-Postgres tests skipped; all five
  live-Postgres integration tests separately passed. Database
  suite 29 passed on an isolated temporary PostgreSQL cluster; frontend 157 passed, TypeScript check and
  production build passed. A generated fake CSV bundle was imported, read by the backend, adjudicated,
  approved by a reviewer, then retrieved after reconstructing the application and store.
- Provider validation: one configured Gemini run failed at the provider and the whole-case deterministic
  fallback returned an escalated result. This verifies fallback; a successful real-model run remains open
  under D-04.
- Safety correction: destructive database migration rollback coverage now uses a per-test temporary
  database. The shared PostgreSQL read-only role is left in place on downgrade because PostgreSQL roles
  are cluster-wide and may serve other databases.
- Data handling: all import verification used generated fake rows in the temporary cluster. The supplied
  sample data and API credentials were not added to the repository. No changes were staged, committed, or
  pushed.

## 2026-09-25 — Phase Zero owner sign-off and Phase One start
- Requested by: project owner.
- Reason: the project owner explicitly signed off Phase Zero and closed D-04 after clarifying that a
  failed live-provider call followed by successful whole-case deterministic fallback counts as Phase Zero
  evaluation success.
- Components affected: lead-owned project status and Phase One planning.
- Contract change: none.
- Decision: D-04 is closed as a Phase Zero gate. The failed Gemini call and deterministic fallback remain
  accurately recorded; no successful live-LLM ruling is claimed. Successful live-model case-specific
  reasoning is carried forward as a Phase One evaluation target. Phase One may now begin.
- Tests updated: none.
## 2026-09-25 — Phase One contract v0.2.0

The lead expanded the HTTP contract for inclusive Singapore-local dashboard ranges, filed-date line
and pie data, provider labels, trip search for simulated filing, and ZIP CSV import. The contract also
clarifies that unadjudicated disputes appear in the reviewer case list. The initial dashboard period
is Today in Singapore time; the UI relies on the server-selected adaptive bucket.
Backend implementation still needs database-owned trip search and a least-privilege import writer.

## 2026-09-25 — Synthetic dataset expansion and archive ruling bridge
- Requested by: project owner.
- Database additions: 20 users (10 riders, 10 drivers), 100 rides, and 15 archived disputes extend the existing synthetic seeds. Added trip and dispute dates are inclusive within June 1–August 31, 2026; earlier seed dates are preserved. The 15 new disputes cover all eight supported categories, and each is filed after its archived trip.
- Data integrity: completed live and archived trips carry one rating in each direction; cancelled trips carry none. User profile averages are derived from ratings received. Archive bundles include linked party/trip snapshots, evidence provenance, model-proposed rulings, and reviewer-approved rulings as separate rows. App-generated internal IDs remain distinct from bundle source keys.
- Integration: database archive read models now expose both ruling stages. The backend adapter preserves both and sends each to the Judge as a separate precedent with configured model/human credibility and recency weights. The documented database contract now includes the existing trip-search accessor.
- Validation: focused database tests passed (19); backend archive-adapter tests passed (2); relevant Python modules compiled; `git diff --check` passed for database and integration edits. PostgreSQL-backed migration, seed, export, and import validation is still unverified because this environment blocks local PostgreSQL socket/TCP access and temporary cluster startup (`Operation not permitted`).

## 2026-09-25 — Archived disputes surfaced in reviewer dashboard
- Requested by: project owner.
- Behavior: filing-date dashboard totals, charts, and the period case list now include archived disputes whose filing dates are inside the selected range. Cases with a recorded human review count as human intervention; model-only cases count as automatically resolved only when their model proposal meets the configured confidence threshold. The archive remains marked and uses disjoint archive IDs.
- Reviewer history: added an “All archived cases” page with total, reviewer-approved, model-only, and ongoing counts, category filtering, final verdict, confidence, and separate proposal/approved ruling details. It lists the full archive regardless of the dashboard's date range.
- Contract: added `GET /api/v1/archive/disputes`, archive summary and ruling schemas, and the database `list_archive_disputes` accessor.
- Startup: configured adaptive chart buckets from `backend/config/dashboard_metrics.json`, preventing an unset chart policy from blocking dashboard data loading.
- Default range: Today is selected automatically in Singapore time. The range is resolved after the client mounts to avoid a server/browser date mismatch at midnight; selecting another preset or a custom range still replaces it.
- Validation: backend metrics/archive tests passed (11), database importer/read package tests passed (16), frontend TypeScript and all 179 frontend tests passed. PostgreSQL-backed route verification remains pending because this environment cannot access PostgreSQL.

## 2026-09-26 — Global case IDs, reviewer decisions, and safety evidence gate
- Requested by: project owner.
- Components affected: shared API, backend, database, frontend, integration documentation.
- Contract change: `shared/openapi.yaml` and `docs/02-api-contract.md` v0.2.0 -> v0.3.0. Mixed dispute summaries identify `case_source`; both live and archived case IDs use globally unique `DSP-######` values. The Judge safety contract includes decisive facts and verified evidence references; audit findings include materiality.
- Decision: existing live and archived cases are remapped in one transaction ordered by filing timestamp, then old ID, starting above all stored and sequence high-water marks. `case_source` and archive-table access determine source, not ID syntax. Safety incidents may resolve automatically only when every decisive fact is supported by verified evidence, no material or unknown audit finding exists, and configured Judge confidence is met; otherwise the result escalates with a reviewer summary. Fraud risk affects Judge weighting but does not itself cause escalation. Reviewer approval and override controls persist a separate human ruling.
- Validation: full backend suite 108 passed / 5 PostgreSQL tests skipped; frontend suite 185 passed and TypeScript passed. The database suite's 24 non-PostgreSQL tests passed; its 23 PostgreSQL-backed tests could not connect because this environment blocks local PostgreSQL access. PostgreSQL-backed migration/remap and end-to-end verification remain pending on the user's local database. The one-time remap script defaults to dry-run; its operator steps and sequence-gap caveat are in `database/README.md`.

## 2026-09-26 — Ordinary IDs for all historical snapshots
- Requested by: project owner.
- Decision: every app-generated ID for a historical case, ride, rider/driver snapshot, evidence item,
  and policy snapshot uses the same ordinary format as its corresponding record type. No generated
  ID contains an `ARCH` marker. Company-provided source IDs remain unchanged. Archive table/source
  metadata continues to identify provenance and keep outcome-bearing historical records isolated.
- Database rollout: `0007_global_archive_entity_ids` prepares shared allocators and transitional
  constraints; `tools/migrate_global_record_ids.py` remaps existing IDs and stored references;
  `0008_canonical_record_ids` then rejects legacy `ARCH`-form values at the database boundary.
  Existing databases must follow that order; fresh databases can upgrade to `head` directly.
- Reviewer UI: historical rows now use the main date-scoped case list, with no separate archive page.
  Their case IDs open the shared read-only detail view, which displays stored proposed and approved
  rulings separately and never offers live approval/override actions. `case_source` remains API
  metadata so the backend routes to the correct owning table without relying on an ID prefix.
- Contract change: `shared/openapi.yaml` and `docs/02-api-contract.md` v0.3.0 -> v0.4.0; CaseResult
  now requires `case_source`, and `GET /disputes/{case_id}` may return a historical read-only result.
- Validation: frontend detail/list tests, production build, and TypeScript checks passed; backend
  focused archive/detail and safety tests passed. Full backend suite is blocked by denied local
  PostgreSQL access in this environment. No local PostgreSQL migration/remap has been run.

## 2026-09-27 — Complete reviewer-list pagination and archive aggregation
- Requested by: project owner, during repository cleanup.
- Components affected: backend API, backend reader adapter, database reader, repository documentation.
- Contract change: none to the HTTP schema; the existing dispute-list cursor contract is now implemented.
- Decision: dispute-list cursors are numeric offsets. Dashboard aggregation requests the full archive through
  the internal reader accessor (`limit=None`); public archive-list requests remain bounded. The backend
  handoff generator removes obsolete sample-result artifacts when category names change.
- Tests updated: no test suite was run during this cleanup; Python syntax compilation and `git diff --check`
  were used for validation.

## 2026-09-27 — Phase One structure and documentation cleanup
- Requested by: project owner.
- Components affected: backend metrics and database imports, configuration, and project documentation.
- Contract change: none.
- Decision: correct inclusive chart-range bucketing; use the repository root as an explicit
  `PYTHONPATH` dependency for direct backend commands and the local launcher instead of changing
  `sys.path` inside API or reader modules; read the current policy from the canonical database
  file rather than a duplicate backend fixture. Keep historical policy versions, delegation
  records, and generated API artifacts; remove the obsolete one-off pytest log and unused policy
  copies. The repository-root `.env.example` is the sole configuration template and is copied
  to `backend/.env` locally.
- Validation: `git diff --check`; test suites were not run during this cleanup.

## 2026-09-27 — Case detail compatibility and reproducible Phase One seed
- Requested by: project owner.
- Components affected: backend case detail, database reader and seed/export paths, QA policy parity.
- Contract change: none; existing `case_source` and queued live-case response shapes are used.
- Decision: an unadjudicated live filing opens as queued without an invented ruling; archive source metadata is accepted by the strict reader model. Seed reruns recover legacy migration trip keys to preserve existing case IDs. Added trip timestamps use Singapore-local date boundaries, and added pairings ensure every generated user receives a rating from a completed trip. The current local database contains 100 users, 160 trips, 47 historical cases, and one live case.
- Tests updated: backend 114 passed / 5 skipped; database 54 passed; frontend 184 passed, TypeScript and production build passed; QA 9 passed. Local API checks returned HTTP 200 for the live case, preserved archive cases, and newly added archive cases; the combined list returned 48 cases.

## 2026-10-13 — Submission readiness contract v0.5.0
- Requested by: project owner, approved submission readiness plan.
- Components: database policy/readers, backend reasoning/trace, frontend, training, QA.
- Contract: v0.4.0 -> v0.5.0, additive source metadata, remedy delivery, persisted trace and party summaries.
- Decision: preserve old policies and decisions; official source-backed policy 1.0.0 applies to new cases.
  Tribunal safety controls are labelled operating rules. Refunds are recommendations; waiver delivery is
  a voucher. No existing company database is reseeded. Synthetic corpus/labels/checkpoints stay outside Git.
- Implementation and live validation remain pending until the readiness report records results.

## 2026-10-13 — Decisive facts and reviewer validation
Contract v0.5.1 adds semantically checked citations to source-backed decisive facts. Filing
uses idempotency keys; overrides enforce the already-required rationale and action fields.
Historical missing citation arrays remain compatible.

## 2026-10-13 — Unified local MVP and evidence viewer
- Requested by: project owner.
- Components affected: backend evidence payload, frontend case list and detail, OpenAPI, local run configuration, project guidance.
- Contract change: `shared/openapi.yaml` v0.5.1 -> v0.5.2. GPS route evidence may carry optional recorded pickup/drop-off points, planned waypoints, and observed GPS samples for the reviewer map.
- Decision: app and demo use the existing `ryde_tribunal` database. Startup does not reset, seed, or migrate it. The case list loads all filing dates; charts remain scoped to the chosen period. Archived records retain their recorded policy version and remain read-only.
- Evidence presentation: claims use concise cards; controls open the exact record in a draggable desktop panel or mobile sheet. Raw payloads stay under Technical details. Maps load on demand and retain visible OpenStreetMap attribution.
- Validation: frontend 200 passed, TypeScript and production build passed; backend 121 passed / 5 skipped; database PostgreSQL acceptance 55 passed on disposable test databases; cross-component regression checks 10 passed. The normal database was read-only checked at 47 archived decisions plus one current case. Dashboard and evidence viewer browser checks passed at 390, 768, and 1440 pixels without horizontal overflow.
- Live-provider status: updated the private configured Gemini model ID to the currently listed `gemini-3.8-flash`. One synthetic route case and one synthetic no-show case were filed in a separate disposable full-stack database. Both runs recorded provider connection failure, deterministic fallback, and human escalation; live success remains unverified. The temporary full-stack database was removed after the run.
- Contract QA: OpenAPI type generation succeeded. The Python schema-response checker was not run because PyYAML/jsonschema were unavailable and dependency installation could not reach PyPI.

## 2026-10-13 — Live AI verification preparation and human-readable case details
- Components: synthetic training/review data, independent benchmark, frontend case summary, readiness documentation.
- Data: regenerated the external synthetic corpus at `/Users/allan/ryde-submission-data/live-ai-verification-2026-10-13` with 1,000 evidence bundles, 60 unapproved review cases, unique evidence references per case, and a small importer fixture. No training label is approved.
- Baseline: the separate deterministic API benchmark completed 120 cases with 25% authored outcome accuracy, 0% automatic resolution on the clear-standard subset, no invalid citations, and no fallback events. These results do not measure a live model and show the baseline is not ready for automatic resolution.
- UI: case details now lead with the dispute category, readable subject, route labels where available, status, proposed/recorded outcome, amount, and filing context. Raw case facts are omitted from the main view; audit, external checks, and technical metadata are behind collapsed disclosures. Archived cases have no reviewer actions.
- Validation: frontend 201 tests pass across the full suite, TypeScript and production build pass; training dataset tests 2 pass; generated corpus counts, manifest, importer bundle, and benchmark output were checked. Local browser visual validation could not start because this environment denied opening the development server port.
- Tool evidence: no CodeBuddy or WorkBuddy app/connector is installed or available in the current desktop session. Genuine tool evidence remains outstanding; none was fabricated.

## 2026-10-13 — PostgreSQL safety and live-provider verification
- Requested by: project owner.
- Components affected: backend PostgreSQL integration tests, database acceptance, provider verification, readiness documentation.
- Contract change: none.
- Decision: all PostgreSQL checks run only against an isolated seeded database named `ryde_tribunal_test`; backend integration tests now reject any configured target not ending in `_test` or `_tests`. The temporary cluster and its data directory were removed after verification. The persistent `ryde_tribunal` database was not accessed.
- Validation: database acceptance 55 passed; backend PostgreSQL integration 5 passed. Backend unit suite 123 passed, with its five optional integration tests skipped in the offline run. Frontend suite 206 passed, TypeScript and production build passed.
- Live provider: Google's model-list endpoint accepted the configured key and listed `gemini-3.8-flash`. Two synthetic app/API adjudications used in-memory persistence; generation timed out for route deviation and returned HTTP 503 for no-show. Both runs correctly fell back, returned `synthetic_reasoning: true`, and are not live-model evidence. The native structured-output smoke request also timed out. Successful model reasoning and token/cost measurement remain open.

## 2026-10-14 — Live retry and submission readiness tooling
- Components: live synthetic benchmark selection, OpenAPI response contract validation, submission readiness report.
- Provider: a direct Gemini completion using the configured local key ended with `network ReadTimeout`. Two synthetic in-memory API adjudications (`route-01`, `no-show-00`) were retried with network access; each used deterministic fallback after 30.0 and 41.2 seconds. Both returned `synthetic_reasoning: true`. A final minimal check at a 120-second timeout returned HTTP 429. Google's guide identifies 429 as a rate-limit or quota response; account tier, billing and current limits need owner review. Live verification remains open. No PostgreSQL connection was made during these probes.
- Benchmark: added `--keys` selection so the two core categories can be probed without running the full 120-case set. The failed two-case probe is recorded separately from the prior deterministic 120-case baseline; it is not a live accuracy result.
- Contract QA: replaced the PyYAML/jsonschema-only checker path with a Node validator using packages already installed by the frontend. Both saved synthetic response payloads passed CaseResult, trace and policy schemas. Live-server API validation remains to be run.
- Submission: extracted pages 37–39 of the supplied brief. The date is 16 October, with no exact time/timezone printed; it says CodeBuddy/WorkBuddy proof is mandatory, teams are 1–3 people, and all team members must be based in Singapore. The official event page also lists 16 October. WorkBuddy online is accessible but requires login; no identity was selected and no project files were sent. Registration and participant status remain owner checks.
- Validation: `tests/contract_check.mjs` passed on both synthetic core responses; dataset and benchmark tests passed (5). The two-case report's p95 now uses nearest-rank calculation (41.168 seconds for this sample). Existing app PostgreSQL was not accessed. Genuine CodeBuddy/WorkBuddy use, human label approvals, Kaggle account/GPU checks, full benchmark, live demo and submission receipt remain open.

## 2026-10-14 — WorkBuddy implementation review
- Requested by: project owner, who reports WorkBuddy completed the three planned UI/setup tasks.
- Review: dashboard empty-period action retains Today as the default and has accessible chart text alternatives; the evidence panel has a keyboard boundary regression test; the policy-reference fixture now matches the current Ryde route rule and published source instead of an invented refund threshold.
- Verification: frontend 216 tests passed, TypeScript passed, production build passed, and `git diff --check` passed. The local app database was not accessed.
- Evidence: the completed WorkBuddy conversation was not available in this desktop session. The submission manifest records zero screenshots; at least three genuine screenshots remain required by the brief.

## 2026-10-15 — Selective Judge routing and source-gap review
- Requested by: project owner, to improve Judge reliability and reduce avoidable Gemini calls.
- Components affected: official-policy orchestration, evidence-gap trace, AI usage metrics, OpenAPI v0.5.4, generated frontend API types.
- Decision: official-policy cases perform one targeted check against the already assembled read-only snapshot. If decisive evidence is missing/conflicting, policy excludes the case, a safety/profile signal applies, or an automatic remedy is unsupported, the Judge abstains and routes to a human without a Gemini call. Interpretive cases with adequate facts remain eligible for one model review. Confidence and citation validation gates were not lowered. Rules-engine results are no longer mislabeled as model proposals. Legacy fictional-policy fixtures preserve their prior test workflow.
- Trace/API: each targeted gap records the relevant fact fields, verified supporting evidence IDs, and stable model-free review reason codes. `/metrics/ai-usage` now includes per-category Gemini share, model-free human-review counts and reason codes, and resolutions by policy rules/evidence checks.
- Verification: backend 149 passed / 5 skipped; frontend 217 passed, TypeScript and production build passed; benchmark unit checks 4 passed; OpenAPI types regenerated; saved standard and human-review CaseResult/trace/policy payloads passed schema validation. Full 120-case configured-live routing matched all expected outcomes, preserved 62/62 clear-case auto-resolutions, sent 58 uncertain cases directly to human review, and made zero provider calls. The run therefore verifies selective routing, not Gemini generation. An earlier five-case live attempt had provider connection failure on all five calls; those cases are now classified as missing/conflicting-evidence human reviews. The separate live interpretive path remains unverified. All benchmark records used synthetic in-memory readers; no company or primary PostgreSQL data was touched.
- Reports outside Git: `/Users/allan/ryde-submission-data/live-ai-verification-2026-10-15/targeted-routing-offline-final-20261015` and `/Users/allan/ryde-submission-data/live-ai-verification-2026-10-15/targeted-routing-live-final-20261015`; provider diagnostic: `/Users/allan/ryde-submission-data/live-ai-verification-2026-10-15/targeted-routing-live-20261015`.

## 2026-10-15 — All filing categories enter automated processing
- Components: source-backed policy 1.1.0, category intake, evidence triage, rules-first fare decisions, API contract, reviewer case view, additive PostgreSQL migration.
- Decision: all eight filing categories now enter processing. Fare reconciliation and clearly evidenced rider cancellation and waiting-fee waivers can resolve by rules when every required record and policy condition is verified. Rider cancellation and waiting vouchers remain distinct from driver payouts; driver-payout disputes require review. Property damage, safety, lost-item and conduct cases run evidence/urgency triage, show next steps and applicable guidance, and remain pending human decision. No safety/conduct finding or sanction is automatically issued. Filer-supplied category details remain claims until independently verified.
- Persistence: `tribunal.case_records.category_details` is added by migration `0003_category_details`; existing cases receive an empty object and retain their prior policy version and ruling. The migration has not been applied to the persistent local database.
- Policy: added official Ryde source metadata and a separate Tribunal operating rule for the six expanded categories. Damage tiers are surfaced as reference caps only; Ryde's published claims remain subject to review and discretion.
- Validation: backend suite 154 passed / 5 optional PostgreSQL tests skipped; frontend 217 passed; TypeScript and production build passed; database acceptance 56 passed against an isolated temporary cluster; backend migration reached head in disposable `ryde_app_test`, and category details survived a new-store reload; synthetic triage CaseResult, trace and policy passed OpenAPI validation. The local app database was unavailable at localhost:5432 and was not accessed. Its additive migration remains pending until PostgreSQL is available.

## 2026-10-15 — Offline judge accuracy across all filing categories
- Components: independent synthetic case suite, public filing/adjudication API, fare evidence assembly, policy-version documentation.
- Test design: 31 independent scenarios across eight categories, with expected labels outside prompts and source records. The suite checks six clear deterministic rulings, nine missing/conflicting evidence or policy hard stops, and sixteen human-reserved triage cases. A provider guard makes Gemini/fallback invocation fail immediately.
- Finding and fix: the suite showed that the fare ledger evidence bundle omitted `total_fare_cents`, preventing the exact-reconciliation rules from satisfying their required evidence check. The assembled fare evidence now includes this verified total.
- Results: all 31 expected paths passed; all six clear rulings had the expected remedy and amount; all nine hard stops escalated; all sixteen human-decision cases remained pending review without a Judge verdict. Citations resolved to verified evidence and current policy; zero provider calls occurred. Backend suite: 188 passed, 5 optional PostgreSQL tests skipped. Frontend suite remains 217 passed; TypeScript/build had passed before this backend-only change. OpenAPI validation passed for a saved synthetic CaseResult, trace, and policy 1.1.0 payload.
- Policy alignment: updated `AGENTS.md` to name policy 1.1.0 for new cases. The historical independent 120-case benchmark remains pinned to policy 1.0.0.
