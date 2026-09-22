# 02 — Contracts (draft v0.1.0, frozen on Phase Zero approval)

Two contracts: the **HTTP contract** between frontend and backend, and the **database read contract**
between backend and database. Neither side may depend on anything not written here.

## 1. Conventions

- JSON, `snake_case`, UTC ISO-8601 with `Z`.
- Money is an integer of **cents** plus a currency code — never a float. `{"amount_cents": 325,
  "currency": "SGD"}` is the `S$3.25` partial refund in the handoff.
- Identifiers: `RIDE-000123`, `DSP-000045`, `EV-000789`, `USR-R-000012` (rider), `USR-D-000034`
  (driver). Archive namespace is disjoint: `RIDE-ARCH-*`, `DSP-ARCH-*`.
- Errors: `{"error": {"code": "…", "message": "…", "details": {…}}}` with codes
  `validation_error`, `not_found`, `conflict`, `database_unavailable`, `provider_unavailable`,
  `internal_error`. **A failure never returns a ruling.**
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
File a dispute. Body: `category` (`route_deviation|no_show|property_damage|safety_incident`),
`ride_id`, `filed_by` (`rider|driver`), `subject`, `description`, optional
`claimed_amount: Money`, optional `attachments[]`.
→ `201 {"case_id": "DSP-000045", "status": "queued"}`

### `POST /api/v1/disputes/{case_id}/adjudicate`
Runs the tribunal. → `200 CaseResult`. Idempotent per `Idempotency-Key`, and concurrency-safe: the
implementation must hold a row-level lock or a unique constraint on the key, not a read-then-write check.

### `GET /api/v1/disputes/{case_id}` → `CaseResult`
### `GET /api/v1/disputes?status=&category=&urgency_min=&needs_review=&from=&to=&sort=&limit=&cursor=`
→ `{"items": [CaseSummary], "next_cursor": null}`

### `GET /api/v1/metrics/overview?tz=Asia/Singapore`
→ `{"filed": {"today": n, "week": n, "month": n}, "auto_resolved": n, "human_review_pending": n,
"overridden": n}`

### `GET /api/v1/metrics/timeseries?granularity=day&from=&to=`
→ `{"points": [{"date": "2026-09-22", "automatic": 7, "human_intervention": 2}]}`

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
  "ride_id": "RIDE-000123",
  "category": "route_deviation",
  "status": "resolved | escalated | pending_review | overridden",
  "synthetic": true,
  "synthetic_reasoning": false,
  "policy_version": "ryde-policy-0.1.0",
  "created_at": "2026-09-22T07:08:00Z",
  "case_facts": { "…": "denormalized ride summary, no outcome fields" },
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
      "provider": { "kind": "llm", "model": "…" }
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
    "policy_references": ["RP-ROUTE-003", "RP-FARE-001"],
    "precedent_references": ["DSP-ARCH-000017"],
    "precedent_binding": false,
    "measurements": { "deviation_pct": 34.2, "planned_distance_km": 13.7, "actual_distance_km": 18.4 },
    "escalation": { "escalated": true, "reasons": ["confidence_below_threshold", "high_impact"],
                    "human_review_summary": "…" },
    "provider": { "kind": "llm", "model": "…" }
  },
  "external_findings": [],
  "external_unavailable": false,
  "urgency": 0.61,
  "case_history": []
}
```

`CaseSummary` is `case_id, ride_id, category, status, confidence, ruling_type, urgency,
needs_review, created_at, synthetic_reasoning`.

## 4. `Evidence`

```json
{
  "evidence_id": "EV-000789",
  "case_id": "DSP-000045",
  "class": "gps_telemetry | chat_log | fare | profile_history | attachment | external",
  "source": "system_record | rider_submitted | driver_submitted | external",
  "recorded_at": "2026-09-22T06:40:00Z",
  "provenance": { "table": "ride_gps_samples", "row_ids": ["…"], "collector": "app_v3" },
  "verification": { "status": "verified", "method": "device_gps_signed", "uncertainty_pct": 2.5 },
  "visibility": "both | rider_only | driver_only | reviewer_only",
  "payload": { "…": "class-specific" }
}
```

`verification.status ∈ verified | unverified | disputed | unverifiable`. Precedence per integrity
rule I-7 in `docs/04-integrity-rules.md`.

## 5. Database read contract — **read-only, eight accessors**

The backend reads through documented accessors only; the frontend never connects to Postgres. This
contract has **no write surface**. That is deliberate: the data layer the tribunal reasons over cannot be
mutated by the thing doing the reasoning (integrity rule I-2).

| accessor | returns |
|---|---|
| `get_ride(ride_id)` | ride header, timestamps, estimates, fare header |
| `get_route(ride_id)` | planned route, actual route, waypoints, stops, durations |
| `get_gps_samples(ride_id)` | ordered samples with accuracy |
| `get_chat_log(ride_id)` | messages with participant role, timestamp, text |
| `get_fare_breakdown(ride_id)` | components, surge, promo, cancellation fee, adjustments |
| `get_profile(user_id)` | account age, rating pattern, dispute counts, prior classifications |
| `search_archive(category, features, limit)` | advisory precedent from `archive_*`, **disjoint ids** |
| `get_archive_case(archive_case_id)` | one archived case in full. Accepts `DSP-ARCH-*` ONLY and raises on a live `DSP-*` id |

Live accessors return **no** outcome fields (integrity rule I-2). `search_archive` and `get_archive_case`
are the only sources of verdicts, both advisory, both confined to the `DSP-ARCH-*` namespace.

`get_case(case_id)` was listed here in draft v0.1.0 and has been **removed**, because the two
specialists read it two different and equally defensible ways: the backend expected the *live* dispute
under adjudication, the database specialist implemented it as an *archived* case. That collision is
dangerous rather than merely untidy — the backend would have called it for the case being adjudicated and
received an outcome-bearing archive record, which is the "case looks up its own answer" failure integrity
rule I-2 exists to prevent. The live case belongs to the backend's own `tribunal` schema; the archive path
is now named `get_archive_case` so the two can never be confused again, and it rejects a live id outright.

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
them: precedent arrives only through `search_archive` / `get_archive_case`, keyed to `DSP-ARCH-*`, and is
advisory.
