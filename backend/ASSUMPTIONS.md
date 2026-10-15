# Backend assumptions — historical implementation record

This file records decisions and observations made during development. It is not the current
setup guide; use `backend/README.md`, `docs/PHASE-ZERO-STATE.md`, and the current contract for
present behavior. In particular, current policy tests use the canonical database policy and
the backend no longer falls back to a duplicate current-policy fixture.

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
  `assert_archive_id` (`DSP-######`). Live and archive cases share this shape; the archive
  reader remains scoped to archive tables and never falls through to the live tribunal store.
  Test: `tests/test_i2a_archive_id_guard.py`.
- Evidence bundle assembled at adjudication from `ride_data` reads + party submissions in
  `tribunal`; party submissions (attachments) are stored `unverified`.
- I-5 review finding addressed with BOTH options: (a) the mock varies argument STRUCTURE per
  case via `_structure_key` (five skeletons keyed to the ruling-relevant finding); (b) a
  text-independent structural assertion (`_assert_structural_distinctness`: cited-evidence
  Jaccard distance) is now the binding guarantee, and the text-similarity ceiling is set to
  0.95 on independent grounds (a template-detection cap, not fitted to the current numbers).

## A-0d — Evidence bundle assembled at adjudication + fare-excess finding
Lead in-process review of the integrated app found the tribunal issuing a confident ruling with
ZERO evidence and no escalation. Root cause: nothing assembled the evidence bundle in the real
path (the fixture builders hand-populated it offline). Fixed:

- `orchestration/facts.py::assemble_evidence_bundle` builds the bundle at adjudication from
  `ride_data` reads (route/gps → distance & arrival, fare ledger → quoted/charged/fee, chat →
  contact, wait) as VERIFIED `system_record` `Evidence`, each with a stable case-unique
  `EV-\d{6}` id (base derived from the ride id so distinct cases cite distinct id sets — I-5),
  `provenance` naming the source table + row ids, correct `visibility`, and a payload keyed by
  `field_path` and grouped by `_question`. Party submissions join as `unverified`.
- Advocates now cite these (non-zero claims/citations with real `field_path`/`observed_value`),
  so I-3 has something to validate; `judge.evidence_references` lists the verified deciding
  records; `GET /evidence/{id}` resolves every id (the bundle is persisted to the store).
- RP-EV-003 made a HARD guarantee: an empty bundle or an absent deciding record forces the case
  insufficient and caps confidence below the escalation threshold, so a confident ruling on no
  evidence is IMPOSSIBLE. Test: `tests/test_rp_ev003_empty_bundle.py`.

**Fare-excess finding (explained, fix applied).** On seeded RIDE-000001:
`quoted_fare_cents=1160`, `total_fare_cents(charged)=970` (base 350 + distance 383 + time 157 +
waiting 0 + surge 0 + **platform_fee 80** = 970), deviation = (11.49−7.75)/7.75 = **48.3%**. The
old ruling was a S$3.86 "refund of the excess" = `_estimate_excess = quoted × (dev−15)/100 =
1160 × 0.333 = 386c` — a **deviation-derived phantom refund**, wrong because the rider was
charged **190c LESS** than quoted; there was no overcharge to refund. The fare field NAMES are
accurate (`total_fare_cents` is what the rider paid; it is below `quoted_fare_cents`), so this is
a code bug, not a data-contract mislabel. Fix: a fare-excess refund is now bounded by the actual
overcharge `charged − quoted`; when that is ≤ 0 the ruling is `no_action` (confidence 0.68 →
escalates for goodwill review), never a fabricated amount. `_estimate_excess` removed. RIDE-000001
now adjudicates to `no_action`, escalated, S$0.

## A-0e — Evidence scoping is server-side (no `case_id` query param)
An earlier iteration required a `case_id` query param on `GET /evidence/{id}` to satisfy the
contract's "case-scoped authorization" wording. The lead has since specified (PR #15) that
scoping is resolved SERVER-SIDE from the record's own `case_id`: an evidence id is globally
unique, so requiring the caller to also name the case is redundant and authorizes nothing.
`shared/openapi.yaml` declares exactly one parameter (the path id), so the generated frontend
client sends only the id. Fixed: `GET /evidence/{evidence_id}` takes the id alone, resolves the
owning case from the stored record (`store.find_evidence_global` over assembled bundles, then
`store.find_party_evidence_global` over filed cases), returns the record with its own `case_id`,
and 404s (not 422) on a non-existent id. `visibility` is still honoured. Phase Zero limitation,
accepted per D-07: with one reviewer identity any valid id is retrievable; real authorization is
Phase One. The integration test now iterates EVERY id in `judge.evidence_references` and both
advocates' citations, asserting each resolves 200 with a matching `case_id`.

## A-0f — A remedy must exist: no refund without a positive amount; zero-remedy contradictions escalate
Mirror of the phantom-excess bug on the no_show_charge side: a fee found invalid by policy was ruled
`refund` even when the verified fare record showed `cancellation_fee_cents = 0`, emitting a
figureless refund. Fixed on three levels:

- **Structural (all categories):** `finalize_ruling` (`orchestration/escalation.py`) runs where
  the ruling is finalized — a `refund`/`compensation` without a positive `amount` is downgraded
  to `no_action` and the case is marked insufficient (so it escalates). `assert_ruling_integrity`
  is a last-line invariant on the returned `judge_block`: a monetary ruling with no positive
  amount raises rather than being emitted. Unit test `tests/test_ruling_integrity.py`.
- **Semantic (the mock judge):** the no_show_charge branch establishes the breach once, then rules
  `refund` ONLY when `fee > 0`; a breach with a zero fee is `no_action` at confidence 0.60.
- **Contradiction (RP-EV-003 / RP-ESC-002):** `Orchestrator._fare_contradiction` detects when the
  filing asserts a charge the verified record does not show (no_show_charge fee=0; route overcharge when
  `charged <= quoted`). That forces insufficient → escalation, and the mismatch is written into
  the human-review summary's WHY line, so the reviewer sees the contradiction, not a bare
  `no_action`.

**Agreement with the lead's point-2 reading:** I concur that a zero-fee no_show_charge where the FILING
asserts a fee should ESCALATE, not silently `no_action` — the filing's premise is contradicted by
the verified record, which is exactly RP-EV-003's "contradictory/inconsistent evidence". (If a
no_show_charge arrived with no fee AND no filing assertion of one, that would be a plain `no_action` with
nothing to decide; the code distinguishes the two via `filing_asserts_fee`.)

**Point-3 audit.** route_deviation already refunds only the actual `charged − quoted` excess (A-0d)
— no phantom amount; property_damage / safety_incident are not adjudicated end-to-end in Phase Zero
(D-14) and never produce a monetary ruling (they hit `no_action` / escalate). `finalize_ruling`
guards all four categories regardless, so a remedy without a figure is impossible for any of them.
Integration proof: RIDE-000010 (fee 500) → refund 500; RIDE-000002 (fee 0) → no_action, escalated.

## A-0g — Post-integration UI-defect fixes (five, from live-screenshot review)
1. **Adversarial advocacy (FIX 1).** The Driver Advocate had shared the Rider Advocate's prose
   (both said "the route ran far beyond tolerance", "extreme excess over what was quoted"),
   conceding the rider's overcharge — the adversarial structure collapsing. Rewrote
   `deterministic_mock._qualitative_findings` so EVERY finding is party-directional: the rider
   reads each field as overcharge/breach, the driver reads the same fields favourably (within
   tolerance, justified, meter-accurate, "no overcharge") and never voices a rider-only
   concession. New `tests/test_adversarial_and_ids.py` asserts, on the same case, the two
   arguments are not near-identical (Jaccard < 0.80) and are directionally consistent with each
   party — the class of check the structural I-5 test could not see.
2. **`Citation.valid` always emitted (FIX 2).** The contract made `valid` REQUIRED (PR #20).
   `Advocate.argue` now validates each citation as it is built and emits `valid` on every one, so
   a cleanly-validated case no longer renders every citation "(invalid)".
3. **Evidence ids conform to `^EV-\d{6}$` (FIX 3).** Dropped the suffixed `EV-000123-1` shape.
   The backend owns the case, so it allocates a clean per-case sequence: assembled bundle uses a
   ride-derived base, party submissions a high (900000+) base, fixtures a 700000+ base — all
   disjoint, all six-digit. Test asserts every emitted id matches the pattern.
4. **`invalid_citation_rate` (FIX 4).** Already emitted as a float in [0,1]; confirmed it matches
   the new `AdvocateOutput` shape and is documented as an invalid-CITATION rate (never an
   unsupported-claim rate), per I-3. No change needed.
5. **CORS for the dev origin (FIX 5).** Added `CORSMiddleware` allowing
   `http://localhost:3000` (methods/headers `*`, credentials on). The frontend's Next.js
   rewrites proxy can now be removed.

## A-1 — Policy JSON location and the missing seed file
`docs/02-api-contract.md` §5 names the policy JSON at
`database/seed/policy/ryde-policy-0.1.2.json` as an input, but that file is owned by the
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
observed maxima (~0.82 no_show_charge, ~0.90 route).

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

## A-0c — Integration (canonical policy + Postgres adapter)
Lead integration pass. Two gaps fixed, both inside `backend/`.

**Gap 1 — canonical policy.** `A-1` predicted this: the loader now consumes
`database/seed/policy/ryde-policy-0.1.2.json` UNCHANGED. Its rules use `{id, section, text}`
and it carries a top-level `numeric_thresholds` list. `PolicyRuleDoc.rule_id = Field(alias="id")`
keeps the internal name; `PolicyDocument.threshold_map()` flattens `numeric_thresholds` into the
evaluator's keys (name correspondence only — every value comes from the file);
`as_public_document()` emits `{id, text, category}` per `shared/openapi.yaml`. The backend
fixture is retained ONLY as a clearly-marked test double (fallback when the `database/` tree is
absent); it is no longer the runtime source.

  **Policy TEXT divergence (reported, NOT changed — `database/` is not mine):** 22 of 28 rules
  differ in wording. The pattern is systematic: the canonical file carries the OPERATIVE FIRST
  SENTENCE of each rule; the backend fixture carried the fuller prose from
  `docs/03-mock-policy.md`. Material examples where the canonical text OMITS a remedy/qualifier
  the fixture had: RP-FARE-001 (drops "refund of the excess over the quoted fare"), RP-ROUTE-003
  (drops the recognised-justifications list and the excess-refund remedy), RP-NOSHOW-002 (drops
  "fee is invalid and fully refundable"), RP-EV-002 (drops "on the same factual question … may
  not by itself reverse a finding"). The Judge now reasons over the shorter canonical wording.
  Flagging for the lead: if the intended policy prose is the fuller text, the canonical file
  should be enriched (a database change), not the backend.

**Gap 2 — Postgres adapter.** `app/persistence/postgres_reader.py` calls the database package's
nine accessors and translates its Pydantic models into the backend record shapes — it does NOT
reimplement the SQL (docs/00-ownership.md §3). Selected by config in `main.py`:
`read_database_dsn` set → `PostgresReader`, empty → `PendingDatabaseReader` (default). Missing
row → `None`; `psycopg.OperationalError`/`InterfaceError` → `DatabaseUnavailable` (so a downed DB
returns `database_unavailable`, never a ruling). The accessors read `DATABASE_URL` from the
env, so the adapter sets the read-only DSN around each call.

  **Deviation from the lead's preferred approach, with reason:** the lead asked for a path
  dependency in `backend/pyproject.toml`. That is unworkable AS A BUILD DEPENDENCY: `database/
  pyproject.toml` declares no build-backend package layout, so `uv pip install` fails with
  "Multiple top-level packages discovered in a flat-layout (seed, reader, migrations)". Fixing
  that is a `database/` edit, which I must not make. Instead the adapter puts the repo-root on
  `sys.path` at import time and imports `database.reader` directly — still a genuine dependency
  on the database's accessors + SQL, resolved by path rather than by a wheel. If the lead wants
  a declared path dependency, the database package needs a `[tool.setuptools] packages` (or
  hatch) entry first.

## A-11 — Two connections, two privilege levels
The read path connects as `ryde_backend_readonly` (SELECT only on `ride_data` / `case_archive`),
proven refused-on-write by `test_integration_postgres.py::test_readonly_role_cannot_write_ride_data`.
The backend's own `tribunal` schema is written through a SEPARATE writable connection
(`tribunal_database_dsn`); when configured, `PostgresResultStore` persists cases, evidence bundles,
model work, proposed rulings, reviewer approvals, history, and idempotency in that schema. The
in-process `ResultStore` remains the offline test adapter. The read DSN is a PLAIN psycopg DSN
(`postgresql://…`), not the SQLAlchemy `postgresql+psycopg://` URL — the accessors use psycopg.

## A-12 — LLM failure uses a whole-case deterministic restart
If any advocate or Judge call fails because the LLM is unavailable or returns a malformed
structured response, the orchestrator discards the partial model pass and restarts the case using
the deterministic provider. The deterministic pass is reported through its ordinary provider
metadata and `synthetic_reasoning` flag. Database failures are never caught as provider failures
and cannot produce a ruling.

## A-13 — Categories without automated policy are review-only
The closed filing vocabulary is `route_deviation`, `no_show_charge`, `fare_calculation`,
`other_cancellation_fee`, `property_damage`, `safety_incident`, `lost_item`, and
`conduct_complaint`. `route_deviation`, `no_show_charge`, and `safety_incident` run model
adjudication; safety cases auto-resolve only under the explicit evidence eligibility gate in
RP-SAFETY-001. Other allowlisted categories are filed and stored, then returned as
`pending_review` without model arguments or a proposed ruling.

## A-14 — Historical rulings are context, never controls
The Judge sees up to three prior same-category tribunal cases and archive records as advisory
examples. Model proposals and reviewer-approved rulings are separate objects; reviewer-approved
outcomes are labelled higher credibility. The Judge still has to justify its decision from the
current case evidence and policy. Company trip/profile/evidence imports do not create disputes or
outcomes.

## A-9 — Live case ownership (SETTLED by the 2nd contract change)
Previously OPEN: whether a filed dispute is joined to the reader. **Settled** by the contract
change removing `get_case` (main commit, PR referenced in the handoff). The live case is the
backend's end to end: `POST /disputes` writes it into `tribunal.case_*` (the backend store),
and adjudication reads it back from that same store — there is NO reader accessor for it. The
evidence bundle is assembled at adjudication time from `ride_data` reads (verified system
records, via the seven ride/user accessors, including app events) plus party submissions stored in `tribunal`.
Nothing joins a live case to `case_archive`; no foreign key crosses between them. Precedent
arrives only via `search_archive` / `get_archive_case` (archive-table-scoped; IDs share the
canonical `DSP-######` shape) and is advisory.

## A-10 — Safety signal detection
A `safety_incident` can auto-resolve only when each Judge-listed decisive fact references verified
evidence, the audit has no material contradiction/error/fabrication finding, and confidence meets
the configured threshold. Missing or unknown data escalates. A chat message with `kind ==
"safety_flag"` or `safety == true` remains an independent human-review signal (RP-SAFETY-002).
The database chat schema supplies these markers; detection is isolated in `Orchestrator._safety_signal`.

## Submission contract v0.5.0
Official policy requires current source-backed facts. Old-policy tests retain historical semantics.
Source-backed deterministic fallback always requires review and never invents a voucher.
Trace and party summaries persist inside existing case_result JSON; no migration or dependency added.
Read-only evidence tools use the persisted snapshot, enforce party visibility and three rounds.
Public policy does not establish a route refund formula. Missing service and decisive timing escalate.
