# 02 — Contracts (draft v0.1.0, frozen on Phase Zero approval)

Two contracts: the **HTTP contract** between frontend and backend, and the **database read contract**
between backend and database. Neither side may depend on anything not written here.

## 1. Conventions

- JSON, `snake_case`, UTC ISO-8601 with `Z`.
- Money is an integer of **cents** plus a currency code — never a float. `{"amount_cents": 325,
  "currency": "SGD"}` is the `$3.25` partial refund in the handoff.
- Identifiers: `RIDE-000123`, `DSP-000045`, `EV-000789`, `USR-R-000012` (rider), `USR-D-000034`
  (driver). Archive namespace is disjoint: `RIDE-ARCH-*`, `DSP-ARCH-*`.
- Errors: `{"error": {"code": "…", "message": "…", "details": {…}}}` with codes
  `validation_error`, `not_found`, `conflict`, `database_unavailable`, `provider_unavailable`,
  `internal_error`. **A failure never returns a ruling.**
- Every mutating request sends `X-Reviewer-Id`. Every request may send `Idempotency-Key`; a repeated key
  with a different body is `409 conflict`.

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

### `GET /api/v1/evidence/{evidence_id}` → `Evidence` (full record, case-scoped authorization)

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

## 5. Database read contract

The backend reads through documented accessors only; the frontend never connects to Postgres.

| accessor | returns |
|---|---|
| `get_ride(ride_id)` | ride header, timestamps, estimates, fare header |
| `get_route(ride_id)` | planned route, actual route, waypoints, stops, durations |
| `get_gps_samples(ride_id)` | ordered samples with accuracy |
| `get_chat_log(ride_id)` | messages with participant role, timestamp, text |
| `get_fare_breakdown(ride_id)` | components, surge, promo, cancellation fee, adjustments |
| `get_profile(user_id)` | account age, rating pattern, dispute counts, prior classifications |
| `get_case(case_id)` | dispute header and evidence references |
| `search_archive(category, features, limit)` | advisory precedent from `archive_*`, **disjoint ids** |
| `persist_model_work(case_id, payload)` | durable write of advocate/judge work |

Live accessors return **no** outcome fields (integrity rule I-2). `search_archive` is the only source of
verdicts and it is advisory.

## 6. Write matrix

| component | writes |
|---|---|
| database | migrations, seed, `archive_*`, all `ride_*` and `user_*` seed data |
| backend | `case_*`, `model_work_*`, `ruling_*`, `case_history`, `idempotency_keys` |
| frontend | nothing — API calls only |
