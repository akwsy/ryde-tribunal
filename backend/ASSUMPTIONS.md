# Backend assumptions — Phase Zero

Assumptions the brief (§6) requires recording, plus material choices made where a requirement
was ambiguous. Where an assumption touches material behaviour I could not resolve from the
docs, it is flagged **OPEN** and raised in the handoff rather than silently invented.

## A-0 — Contract change: `persist_model_work` removed; backend owns the `tribunal` schema
Lead-agent contract change merged to main as commit `53eff3f` (PR #2). `docs/02-api-contract.md`
§5 is now an EIGHT-accessor, READ-ONLY contract with no write surface — `persist_model_work`
was removed (a write function had no business in a read contract). §6 makes the backend own
and migrate the `tribunal` schema and its tables (`case_*`, `model_work_*`, `ruling_*`,
`case_history`, `idempotency_keys`); its DB role has `SELECT`-only on `ride_data` /
`case_archive`, enforced in PostgreSQL.

Applied here:
- `DatabaseReader` Protocol reduced to the eight read accessors; `persist_model_work` deleted
  from it, from `PendingDatabaseReader` (main.py), and from `FixtureReader`.
- The orchestrator now persists model work through the backend's OWN layer
  (`ResultStore.persist_model_work` → `tribunal.model_work_*`), injected via the container.
  No shim, no reader write path.
- Added the migration set I now own: `backend/migrations/` (Alembic), models in
  `app/persistence/models.py`, first revision `0001_tribunal_schema` creating the schema and
  five table families. Validated upgrade↔downgrade against a throwaway local Postgres. The
  `idempotency_keys` UNIQUE constraint is the concurrency guarantee at the DB level (contract
  §2). Added dependency `alembic==1.14.0`.
- I do NOT create tables in `ride_data` / `case_archive` and do not treat `ingest_audit` as a
  model-output landing zone (it is the database generator's provenance record).

## A-0b — Second contract change: `get_case` removed; `get_archive_case` + I-2a; live case is the backend's
Lead-agent contract change (rebased onto main). `docs/02-api-contract.md` §5 removed
`get_case` — the two specialists read it two ways (backend: the live dispute; database: an
archived case), which would have handed the case under adjudication an outcome-bearing archive
record (the I-2 failure via an ambiguous name). New rule I-2a: an archive accessor must RAISE
on a live id.

Applied here:
- Deleted every `get_case` call. The live case now lives in the backend `tribunal` store:
  `POST /disputes` writes a `CaseRecord` via `store.save_filed_case`; `adjudicate` and
  `get_evidence` read it via `store.get_filed_case`. No reader accessor for the live case.
- Reader reduced to eight read-only accessors; `get_case` → `get_archive_case`, guarded by
  `assert_archive_id` (regex `^(DSP|RIDE)-ARCH-\d+$`; raises `LiveIdRejected` on a live
  `DSP-*` / `RIDE-*` id). The guard lives on the backend side (`app/persistence/reader.py`),
  not only in the not-yet-existing database reader. Test: `tests/test_i2a_archive_id_guard.py`.
- Evidence bundle assembled at adjudication from `ride_data` reads + party submissions in
  `tribunal`; party submissions (attachments) are stored `unverified`.
- I-5 review finding addressed with BOTH options: (a) the mock varies argument STRUCTURE per
  case via `_structure_key` (five skeletons keyed to the ruling-relevant finding); (b) a
  text-independent structural assertion (`_assert_structural_distinctness`: cited-evidence
  Jaccard distance) is now the binding guarantee, and the text-similarity ceiling is set to
  0.95 on independent grounds (a template-detection cap, not fitted to the current numbers).

## A-1 — Policy JSON location and the missing seed file
`docs/02-api-contract.md` §5 names the policy JSON at
`database/seed/policy/ryde-policy-0.1.0.json` as an input, but that file is owned by the
database specialist and does not exist yet, and I may not create files under `database/`.

Resolution: the loader (`app/policy/loader.py`) resolves the policy document in this order —
(1) `POLICY_PATH` env override, (2) the canonical `database/seed/policy/<version>.json`,
(3) a **backend-owned test fixture** at `backend/tests/fixtures/policy/<version>.json`. The
fixture's content is transcribed from `docs/03-mock-policy.md` and carries rule ids + text +
thresholds ONLY — no remedies (D-18: one JSON source of truth, no policy constants in Python).
At integration the database seed file takes precedence automatically. **This is the one place
I depend on a not-yet-existing input; the transcription is my reading of the prose and should
be diffed against the DB specialist's seed when it lands.**

## A-2 — Prompt structure
Each component receives a structured prompt (`app/models/components.py`, consumed by
`app/providers/deterministic_mock.py`):
- advocates: `{role, party, category, measurements, policy_rules:[{rule_id,text}],
  visible_evidence:[{evidence_id, class, field_path, value, verification, undercuts}],
  currency}`.
- judge: `{role:'judge', category, measurements, policy_rules, thresholds, rider_argument,
  driver_argument, evidence_ids, precedence_notes, currency}`.
The provider returns a JSON object matching a declared response schema. The `openai_compatible`
adapter sends the same structure as a single JSON user message with `response_format:
json_object`.

## A-3 — Advocate evidence restriction and state isolation
Each advocate is restricted to evidence its party may see via `Evidence.visibility`
(`visible_to()` in `app/domain`), enforced BEFORE the prompt is built
(`_visible_evidence_prompt`) and again at citation validation (I-3 check 5). The two advocates
are separate `Advocate` instances that receive independently-filtered evidence and share no
mutable state; each is called once with only its own visible set. The Judge receives both
finished arguments plus the full case context, but the advocates never see each other's output.

## A-4 — I-5 similarity ceiling: **0.90**, with retained numeric magnitudes
## A-4 — I-5 case-specificity: structural variation + a structural binding signal
`tests/test_i5_case_specificity.py` enforces THREE things per category over ≥6 materially
different cases:
1. arguments are never byte-identical (hard);
2. each case cites a distinct evidence-id set, with mean pairwise Jaccard DISTANCE ≥ 0.5
   (`_assert_structural_distinctness`) — a text-INDEPENDENT signal that is the binding
   guarantee of case-specificity;
3. a secondary text-similarity smell test below **0.95** on normalized tokens (ids stripped,
   numeric magnitudes retained).

Reasoning (addressing the lead's I-5 review): text similarity is a weak proxy — shared domain
vocabulary floors it around 0.85–0.90 for two cases in the same qualitative band no matter how
the wording varies, so a ceiling fitted to just clear the current numbers is a weak guarantee.
Two independent fixes instead: (a) the mock varies argument STRUCTURE per case
(`_structure_key` → five sentence skeletons keyed to the ruling-relevant finding), so the frame
differs case-to-case, not just a hot-swapped number; (b) the structural cited-evidence distance
floor in (2) is the real teeth. The 0.95 text cap is set on independent grounds — it detects a
near-duplicate template differing only in stripped ids — and is deliberately NOT fitted to the
observed maxima (~0.82 no_show, ~0.90 route).

## A-5 — Judge is a deterministic-but-case-driven mapper under the mock
The mock provider's Judge role maps (measurements + policy rule text + advocate positions) to
a ruling AT CALL TIME (`_judge` in `deterministic_mock.py`). This is legitimate under I-1
because the mapping lives in the Judge, not the policy layer, and the output varies with the
case. It is labelled `deterministic-mock` everywhere (I-6). The `openai_compatible` adapter
substitutes a real LLM at the same seam with no orchestration change.

## A-6 — Excess-refund computation
For an unjustified route deviation the refund amount is `charged_fare_cents −
quoted_fare_cents` when that excess is positive; otherwise it is estimated from the deviation
over tolerance applied to the quoted fare (`_estimate_excess`). Both are the Judge's
computation from measurements, and the escalation layer caps a refund at the disputed fare
component (D-11) — a remedy above the cap escalates rather than auto-resolving.

## A-7 — Idempotency store (in-process) is the unique-constraint analogue
`ResultStore.claim_idempotency` performs check-and-insert under a single lock, so exactly one
caller runs an adjudication for a given key and concurrent callers wait for and receive that
result. This is the in-memory analogue of the contract's required "row-level lock or unique
constraint" (§2), verified with real threads in `test_idempotency_concurrency.py`. The durable
form is the `UNIQUE (idempotency_key)` constraint in migration `0001_tribunal_schema`; the
SQLAlchemy-backed store swaps in behind the same `ResultStore` surface at integration.

## A-8 — Running server without the DB reader returns `database_unavailable`
`app/main.py` wires a `PendingDatabaseReader` (every one of the eight read accessors raises
`DatabaseUnavailable`) until the database specialist's reader is integrated. A live server
therefore returns `database_unavailable` and never a fabricated ruling. Tests inject
`FixtureReader` at the same seam. Model-work persistence does NOT go through the reader (the
read contract has no write surface); it goes through the backend-owned store.

## A-9 — Live case ownership (SETTLED by the 2nd contract change)
Previously OPEN: whether a filed dispute is joined to the reader. **Settled** by the contract
change removing `get_case` (main commit, PR referenced in the handoff). The live case is the
backend's end to end: `POST /disputes` writes it into `tribunal.case_*` (the backend store),
and adjudication reads it back from that same store — there is NO reader accessor for it. The
evidence bundle is assembled at adjudication time from `ride_data` reads (verified system
records, via the seven ride/user accessors) plus party submissions stored in `tribunal`.
Nothing joins a live case to `case_archive`; no foreign key crosses between them. Precedent
arrives only via `search_archive` / `get_archive_case` (`DSP-ARCH-*` only) and is advisory.

## A-10 — Safety signal detection
A `safety_incident` category always escalates (RP-SAFETY-001). Additionally, a chat message
with `kind == "safety_flag"` or `safety == true` is treated as a safety signal that forces
escalation even on an otherwise-confident fare ruling (RP-SAFETY-002). The exact schema of a
safety signal in the chat log is the database's; I assumed these two markers and isolated the
check in `Orchestrator._safety_signal`.
