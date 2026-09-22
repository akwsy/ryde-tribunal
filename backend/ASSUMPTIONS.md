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
`tests/test_i5_case_specificity.py` normalizes advocate argument text by stripping evidence
IDS but RETAINING numeric magnitudes, then requires pairwise Jaccard similarity below **0.90**,
AND that arguments are never byte-identical, AND that each cites a distinct evidence-id set.

Reasoning: a measured figure (34% vs 80% deviation; a 250c vs 600c fee) is legitimate
case-specific content — an argument that cites the actual value is reasoning about the case,
not boilerplate — so stripping numbers (as a naive normalizer would) discards real signal and
makes two genuinely different cases look identical. Stripping only ids catches a template that
differs solely in the trivially-unique evidence id, while tolerating the shared domain
vocabulary two same-outcome-family cases legitimately use. The distinct-evidence-set and
never-identical checks are the hard teeth; the 0.90 ceiling is the smell test. Measured
maxima on the current corpora: no_show 0.885, route_deviation 0.872.

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

## A-9 — `filed` disputes vs the DB reader (OPEN, non-blocking)
`POST /disputes` records a filed dispute in-process and returns a `case_id`, but adjudication
reads the case + ride facts through the DB reader (`get_case`). In Phase Zero the two are not
joined: a filed dispute is not automatically visible to `get_case` (that write path is the
database's `case_*` tables, write matrix §6). Tests seed the reader's case directly. **OPEN:
whether the backend should persist the filed dispute into `case_*` for the reader to return,
or whether filing and the ride/evidence record are joined by the database at integration.**
I assumed the latter (backend owns `case_*` writes per §6, but the ride/evidence facts come
from the database's seed), and left the seam explicit rather than inventing a cross-store join.

## A-10 — Safety signal detection
A `safety_incident` category always escalates (RP-SAFETY-001). Additionally, a chat message
with `kind == "safety_flag"` or `safety == true` is treated as a safety signal that forces
escalation even on an otherwise-confident fare ruling (RP-SAFETY-002). The exact schema of a
safety signal in the chat log is the database's; I assumed these two markers and isolated the
check in `Orchestrator._safety_signal`.
