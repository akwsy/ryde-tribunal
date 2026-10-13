# 02 — Contracts (v0.4.0)

Two contracts: the **HTTP contract** between frontend and backend, and the **database read contract**
between backend and database. Neither side may depend on anything not written here.

## 1. Conventions

- JSON, `snake_case`, UTC ISO-8601 with `Z`.
- Money is an integer of **cents** plus a currency code — never a float. `{"amount_cents": 325,
  "currency": "SGD"}` is the `S$3.25` partial refund in the handoff.
- Identifiers: `RIDE-000123`, `DSP-000045`, `EV-000789`, `USR-R-000012` (rider), `USR-D-000034`
  (driver). Live and archived disputes share one globally unique `DSP-######` sequence. For each
  entity type, archived trips, users, and evidence share the corresponding ID sequence with live
  records: `RIDE-######`, `USR-R-######` / `USR-D-######`, and `EV-######`. Provenance and
  source-table metadata distinguish source; IDs do not. Company-provided IDs are retained unchanged
  in separate source-ID fields.
- Errors: `{"error": {"code": "…", "message": "…", "details": {…}}}` with codes
  `validation_error`, `not_found`, `conflict`, `database_unavailable`, `provider_unavailable`,
  `model_output_invalid`, `internal_error`. **A failure never returns a ruling.**
- Every mutating request sends `X-Reviewer-Id`. Every request may send `Idempotency-Key`; a repeated key
  with a different body is `409 conflict`.

### Display rules (frontend, authoritative)

**Money.** Format with `Intl.NumberFormat('en-SG', { style: 'currency', currency })`, which yields
`S$3.25`. That is correct for SGD and is what the UI shows. The bare `$3.25` in the original handoff was
prose shorthand, not a display specification. Never do arithmetic on a formatted string, and never divide
`amount_cents` in a template — convert once, in one helper.

**Confidence.** Render as a percentage to **one decimal**: `0.842` → `84.2%`. Keep the raw float
available in a tooltip or `aria-label` for a reviewer who needs the exact value.

One hazard worth stating explicitly, because it is the kind of bug that survives review: do **not** derive
the escalation state in the client by comparing the displayed percentage — or the raw float — to the 0.70
threshold. `0.6996` rounds to `70.0%` and would appear to clear a bar it did not clear. The
`judge.escalation.escalated` flag is authoritative and is the only thing the UI may branch on. Display and
decision must never be independently derived from the same number.

## 2. HTTP endpoints

### `POST /api/v1/disputes`
File a dispute. Body: `category` (`route_deviation|no_show_charge|fare_calculation|other_cancellation_fee|property_damage|safety_incident|lost_item|conduct_complaint`),
`ride_id`, `filed_by` (`rider|driver`), `subject`, `description`, optional
`claimed_amount: Money`, optional `attachments[]`.
→ `201 {"case_id": "DSP-000045", "status": "queued"}`

### `POST /api/v1/disputes/{case_id}/adjudicate`
Runs the tribunal. → `200 CaseResult`. Idempotent per `Idempotency-Key`, and concurrency-safe: the
implementation must hold a row-level lock or a unique constraint on the key, not a read-then-write check.

### `GET /api/v1/disputes/{case_id}` → `CaseResult`
Returns a live result or a historical case record from its owning source table. Historical responses
set `case_source` to `archive`, keep `judge` and `advocates` null, expose recorded model/reviewer
rulings separately, and cannot be approved or overridden through live-case actions.
### `GET /api/v1/disputes?status=&category=&urgency_min=&needs_review=&from=&to=&sort=&limit=&cursor=`
→ `{"items": [CaseSummary], "next_cursor": null}`

The Phase One reviewer list includes cases filed directly by the rider/driver workflow even before
adjudication. `created_at` in the list means the dispute filing timestamp. A summary includes
`filed_by`, `case_source` (`live` or `archive`), and `provider` (provider name only); `provider` is
`null` until a model has supplied a result, and is `local deterministic` when the fallback supplied it.
Live and archived identifiers are globally unique even though both use `DSP-######`.

### `GET /api/v1/metrics/overview?from=YYYY-MM-DD&to=YYYY-MM-DD&tz=Asia/Singapore`
Both dates are required and inclusive in the requested timezone. Phase One accepts
`Asia/Singapore`; weeks begin on Sunday. The date filter uses the dispute's filed timestamp. The
response counts live filings and archived disputes in range, cases resolved automatically by a
confident Judge, and cases routed to human intervention. Archive rows with a confident model proposal
and no recorded human review count as automatically resolved. Reviewer-approved archive rulings,
escalations, and below-threshold model proposals count as human intervention. Historical cases appear
as ordinary rows in the same dashboard case list; the selected filing-date range scopes that list.
There is no separate archive page.

→ `{"from":"2026-09-01","to":"2026-09-30","timezone":"Asia/Singapore","filed": n,
"auto_resolved": n,"human_intervention": n}`

### `GET /api/v1/metrics/timeseries?from=YYYY-MM-DD&to=YYYY-MM-DD&tz=Asia/Singapore&group_by=category`
Dates are inclusive in the requested timezone and the series is counted by filing date. The server
selects an adaptive time bucket from the requested range duration and returns the selected bucket in
`granularity`; weekly buckets begin Sunday. Approved `group_by` values are `category`, `status`,
`filed_by`, and `provider`. The chart's default is category. The `review_path` value is excluded.
Production cutoffs are daily through 31 inclusive days, weekly through 365 days, monthly through
3,650 days, then yearly. Configure these values in `backend/config/dashboard_metrics.json`.

→ `{"timezone":"Asia/Singapore","granularity":"day","group_by":"category","points":
[{"date":"2026-09-22","series":[{"key":"route_deviation","count":7}]}]}`

### `GET /api/v1/metrics/breakdown?from=YYYY-MM-DD&to=YYYY-MM-DD&tz=Asia/Singapore&by=category`
Returns pie-chart slices for the same inclusive filed-date range. `by` uses the same dimensions and
defaults to `category` in the UI. A dimension with no value is returned as `unknown` rather than
silently omitted.

→ `{"timezone":"Asia/Singapore","by":"category","slices":[{"key":"route_deviation",
"label":"Route deviation","count":7}]}`

### `GET /api/v1/trips?query=&limit=20`
Searches existing trips for the simulated-filing trip picker. `query` matches the app's internal
`ride_id` and trip details such as the location names; returned IDs are app-generated internal IDs.
The response gives enough detail to identify the selected trip before filing. Company IDs remain
source references and are not accepted as filed `ride_id` values.

### `GET /api/v1/archive/disputes?limit=200`
Returns historical records for backend and internal consumers. The reviewer UI shows those cases in
the ordinary dashboard list. Historical detail opens through the standard
`GET /api/v1/disputes/{case_id}` route and remains read-only.

### `POST /api/v1/imports/company-data`
Accepts a ZIP of related CSV files (`application/zip`) in the versioned format documented in
`database/importer/FORMAT.md`. The server validates the whole archive before writing. Rows whose
company IDs already exist are skipped; rows with new IDs are imported. The response reports counts
by record type for imported and skipped records. Dispute tickets cannot be imported through this
endpoint; a rider or driver files a separate dispute against an existing internal trip ID.

### `GET /api/v1/evidence/{evidence_id}` → `Evidence`

Scoping is resolved **server-side** from the record's own `case_id`. The client sends the evidence id and
nothing else — there is no `case_id` query parameter. An evidence id is globally unique, so making the
caller name the case too would be redundant and would authorize nothing, since the caller supplies both
values. Every id appearing in a `CaseResult`'s `judge.evidence_references` or an advocate's citations must
resolve through this endpoint; a referenced id that 404s or 422s is a defect.

Phase Zero limitation, stated rather than hidden: with a single reviewer identity (D-07) there is no
reviewer-to-case mapping, so any valid evidence id is retrievable. Real authorization arrives with Phase
One auth. `visibility` is still honoured.

### `POST /api/v1/disputes/{case_id}/approve`
Reviewer accepts the proposed resolution. Body: `{"note": "…"}` → `CaseResult`

### `POST /api/v1/disputes/{case_id}/override`
Reviewer overrides a resolved case. Body: `{"ruling_type": …, "recommended_action": …,
"reason_code": …, "rationale": "…"}` where `reason_code` comes from a closed vocabulary
(`policy_misapplied`, `evidence_misweighted`, `evidence_missing`, `fraud_suspected`,
`goodwill`, `safety_override`, `other`). → `CaseResult` with the override appended to
`case_history`, never replacing the original ruling.

### `GET /api/v1/disputes/{case_id}/history` → `[{event, actor_type, actor_id, at, payload}]`
### `GET /api/v1/policy/{version}` → the policy document actually used
### `GET /api/v1/health` → `{"status": "ok", "database": "ok", "provider": "ok|unavailable"}`

## 3. `CaseResult`

```json
{
  "case_id": "DSP-000045",
  "case_source": "live | archive",
  "ride_id": "RIDE-000123",
  "category": "route_deviation",
  "status": "resolved | escalated | pending_review | overridden",
  "synthetic": false,
  "synthetic_reasoning": false,
  "policy_version": "ryde-policy-0.1.2",
  "created_at": "2026-09-22T07:08:00Z",
  "case_facts": { "…": "denormalized ride summary, no outcome fields" },
  "evidence_audit": {
    "findings": [{"party":"rider","claim_text":"…","classification":"contradicted",
      "confidence":0.91,"explanation":"…","evidence_references":["EV-000789"],
      "materiality":"material | non_material | unknown"}],
    "provider":{"kind":"llm","display_name":"Gemini","model":"…"}
  },
  "fraud_assessment": {
    "risk_score":0.28,"confidence":0.72,"influence_weight":2.0,"findings":[],
    "provider":{"kind":"llm","display_name":"Gemini","model":"…"}
  },
  "advocates": {
    "rider": {
      "argument": "natural-language position, case-specific",
      "claims": [
        { "text": "…", "citations": [
            { "evidence_id": "EV-000789", "field_path": "route.actual_distance_km",
              "observed_value": 18.4, "supports": "claim-1" } ] }
      ],
      "policy_references": ["RP-ROUTE-003"],
      "rejected_evidence": [{ "evidence_id": "EV-000791", "reason": "…" }],
      "invalid_citation_count": 0,
      "provider": { "kind": "llm", "display_name": "Gemini", "model": "…" }
    },
    "driver": { "…": "same shape" }
  },
  "judge": {
    "ruling_type": "refund | compensation | no_action",
    "recommended_action": { "description": "partial fare refund",
                            "amount": { "amount_cents": 325, "currency": "SGD" } },
    "confidence": 0.842,
    "reasoning": "natural-language summary",
    "evidence_references": ["EV-000789", "EV-000790"],
    "decisive_facts": [{"fact":"The actual route exceeded the planned route.",
                        "evidence_references":["EV-000789"]}],
    "policy_references": ["RP-ROUTE-003", "RP-FARE-001"],
    "precedent_references": ["DSP-000117"],
    "precedent_binding": false,
    "measurements": { "deviation_pct": 34.2, "planned_distance_km": 13.7, "filing_asserts_fee": true },
    "escalation": { "escalated": true, "reasons": ["confidence_below_threshold", "high_impact"],
                    "human_review_summary": "…" },
    "provider": { "kind": "llm", "display_name": "Gemini", "model": "…" }
  },
  "model_proposed_ruling": {
    "ruling_type": "refund",
    "recommended_action": { "description": "partial fare refund", "amount": { "amount_cents": 325, "currency": "SGD" } },
    "author_type": "model", "decision_origin": "agent", "author_id": "model-name", "credibility": "model_proposed"
  },
  "reviewer_approved_ruling": null,
  "external_findings": [],
  "external_unavailable": false,
  "urgency": 0.61,
  "case_history": []
}
```

For a category without an automated policy implementation, `status` is `pending_review` and
`evidence_audit`, `fraud_assessment`, `advocates`, `judge`, `model_proposed_ruling`, and `reviewer_approved_ruling` are `null`; the response
includes a `human_review_summary`. The case remains filed for a human reviewer. For adjudicated cases,
`model_proposed_ruling` records the model decision. `reviewer_approved_ruling` is a separate human-authored
record populated on approval or override; its credibility is higher than the model proposal. The
`synthetic` flag reports the source of the trip record and does not change retrieval or adjudication.
The evidence audit reports claim-level contradiction, inaccuracy, possible fabrication, lack of support,
or consistency, with references and uncertainty. Fraud assessment is a separate case-specific model output
passed to the Judge; its risk affects weighing but never automatically escalates a case.

`CaseSummary` is `case_id, case_source, ride_id, category, status, confidence, ruling_type, urgency,
needs_review, created_at, synthetic_reasoning`.

## 4. `Evidence`

```json
{
  "evidence_id": "EV-000789",
  "case_id": "DSP-000045",
  "class": "gps_telemetry | chat_log | app_event | fare | profile_history | attachment | external",
  "source": "system_record | company_imported | rider_submitted | driver_submitted | external",
  "recorded_at": "2026-09-22T06:40:00Z",
  "provenance": { "table": "ride_gps_samples", "row_ids": ["…"], "collector": "app_v3" },
  "verification": { "status": "verified", "method": "device_gps_signed", "uncertainty_pct": 2.5 },
  "visibility": "both | rider_only | driver_only | reviewer_only",
  "payload": { "…": "class-specific" }
}
```

`verification.status ∈ verified | unverified | disputed | unverifiable`. Precedence per integrity
rule I-7 in `docs/04-integrity-rules.md`.

## 5. Database read contract — **read-only, eleven accessors**

The backend reads through documented accessors only; the frontend never connects to Postgres. This
contract has **no write surface**. That is deliberate: the data layer the tribunal reasons over cannot be
mutated by the thing doing the reasoning (integrity rule I-2).

| accessor | returns |
|---|---|
| `get_ride(ride_id)` | ride header, timestamps, estimates, fare header |
| `get_route(ride_id)` | planned route, actual route, waypoints, stops, durations |
| `get_gps_samples(ride_id)` | ordered samples with accuracy |
| `get_chat_log(ride_id)` | messages with participant role, timestamp, text |
| `get_app_events(ride_id)` | ordered application events with type, details, provenance and verification status |
| `get_fare_breakdown(ride_id)` | components, surge, promo, cancellation fee, adjustments |
| `get_profile(user_id)` | account age, rating pattern, dispute counts, prior classifications |
| `search_rides(query, limit)` | selectable live trips by internal ID, company ID, rider/driver, or location |
| `search_archive(category, features, limit)` | advisory precedent from `archive_*`; archive source is determined by the accessor, not an ID prefix |
| `get_archive_case(archive_case_id)` | one archived case in full, including linked trip/party/evidence snapshots and separate model-proposed and reviewer-approved rulings. Accepts `DSP-######` syntax but reads only `case_archive`; a live case ID never returns archive data |
| `list_archive_disputes(limit)` | historical cases for the mixed reviewer list and filed-date statistics; internal callers may pass `None` to include the full archive |

Archive accessors return proposal and reviewer-approved ruling stages separately when both exist.
The backend passes them to the Judge as separate precedents. Human-approved rulings receive the
configurable higher credibility weight; the policy remains the higher priority, and recency weights
both ruling stages. The reviewer sees these records in the same date-scoped case list as live cases.

Live accessors return **no** outcome fields (integrity rule I-2). Outcome-bearing archive records are
confined to `case_archive` tables. A single shared sequence assigns globally unique dispute IDs; source
is determined by the database table and the `case_source` field on mixed-list items, never by the ID
prefix. `search_archive` provides Judge precedents; `get_archive_case` and `list_archive_disputes`
support source-isolated retrieval for the shared case list and detail route.

`get_case(case_id)` was listed here in draft v0.1.0 and has been **removed**, because the two
specialists read it two different and equally defensible ways: the backend expected the *live* dispute
under adjudication, the database specialist implemented it as an *archived* case. That collision is
dangerous rather than merely untidy — the backend would have called it for the case being adjudicated and
received an outcome-bearing archive record, which is the "case looks up its own answer" failure integrity
rule I-2 exists to prevent. The live case belongs to the backend's own `tribunal` schema; the archive path
is named `get_archive_case` and remains bound to archive tables even though live and archived IDs share
the same format.

`persist_model_work` was likewise listed here in draft v0.1.0 and **removed**: persisting advocate and
Judge work is a backend concern writing backend-owned tables, and a write function had no business in a
read contract. The backend implements its own persistence against its own schema — see §6.

### Schema ownership

Ownership is enforced in PostgreSQL, not only by convention:

| schema | owner | backend's grant |
|---|---|---|
| `ride_data` | database specialist | `SELECT` only |
| `case_archive` | database specialist | `SELECT` only |
| `tribunal` | backend specialist | full |

The database specialist creates a role for the backend with `SELECT` on `ride_data` and `case_archive`
and no `INSERT`, `UPDATE`, or `DELETE`. A backend attempt to write ride or archive data then fails at the
database, which is a far stronger guarantee than a code review.

## 6. Write matrix

Each component migrates and writes its **own** schema. There is no shared migration set, because a
shared one would make every schema change a cross-specialist negotiation.

| component | owns and migrates | writes |
|---|---|---|
| database | schemas `ride_data`, `case_archive`; migrations under `database/migrations/` | all `ride_*`, `user_*`, `archive_*` tables; `ingest_audit` (its own generator provenance) |
| backend | schema `tribunal`; its own migration set under `backend/` | `case_*` (the filed dispute, its evidence references, and party submissions), `model_work_*`, `ruling_*`, `case_history`, `idempotency_keys` |
| frontend | nothing | nothing — API calls only |

So the backend persists advocate and Judge work itself, through its own persistence layer against
`tribunal.model_work_*`. It does not call into the database specialist's code to do it, and the database
specialist does not provide a write path for it. `ingest_audit` records how the synthetic data was
generated; it is not a landing zone for model output.

**The live case is the backend's, end to end.** `POST /disputes` writes `tribunal.case_*`, and the backend
reads it back from its own schema — there is no accessor for it. An evidence bundle for a case is
*assembled* at adjudication time from `ride_data` reads (verified system records) plus party submissions
stored in `tribunal`. Nothing joins a live case to `case_archive`, and no foreign key crosses between
them: precedent arrives only through `search_archive` / `get_archive_case`, resolved against archive
tables and advisory.

## Submission contract v0.5.0 (2026-10-13)

Additive fields preserve historical results. GET /disputes/{case_id}/trace returns
{case_id, events}; each event has at, actor, event, summary, evidence_ids and optional provider.
Events record real requests, outputs, validation and fallback, not private reasoning.
CaseResult may include trace and party_explanations {rider,driver}. Persist both in the
existing durable case_result JSON; no backend schema migration is needed.
RecommendedAction.delivery is voucher, none, or unspecified. Actions are recommendations only.
Policy rules expose classification (ryde_policy, tribunal_operating_rule, historical_fictional),
optional source {url,title,retrieved_at,effective_from,context}, and services.

Read adapters preserve service_tier, accepted_at, arrival_at, cancellation_timestamp,
scheduled_at, cancellation_actor and waiting_fare_cents when available. App events may
establish absent header facts; unknowns remain unknown. New immutable official policy is
ryde-policy-1.0.0; 0.1.x is historical fictional policy.
Advocates use bounded read-only evidence retrieval over a case snapshot (three rounds maximum),
with party visibility checked on every returned record. The Judge receives validated claims and
full evidence in addition to concise arguments. Unsupported services, policy gaps, decisive
evidence gaps and source conflicts require human review.

### v0.5.1 decisive-fact citations
New source-backed Judge decisive facts must include field/value citations, validated against
the actual case evidence. Historical records may omit the additive citations field. The
Judge cannot support a decisive fact merely by referencing an existing evidence ID.
