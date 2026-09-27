# Ryde Tribunal — Frontend

Next.js reviewer dashboard and dispute case views for Ryde Tribunal.

## Quick Start

```bash
# Install dependencies
npm install

# Generate TypeScript types from the shared OpenAPI spec
npm run generate-types

# Run the dev server (fixture mode — no backend required)
npm run dev

# Run tests
npm test
```

Open [http://localhost:3000](http://localhost:3000) for the reviewer dashboard. Case details
are at `/cases/[caseId]`; simulated filing and company-data import are at `/file-dispute`
and `/import-data`.

## Fixture Mode

When `NEXT_PUBLIC_API_BASE_URL` is not set, the app runs in **fixture mode**.
Fixture responses are synthetic and visibly labelled as "FIXTURE — not production data." A live API
may serve generated seed records and company-imported test records through the same case views.
Repointing to a live backend requires only setting the env var:

```bash
NEXT_PUBLIC_API_BASE_URL=https://api.ryde-tribunal.example npm run dev
```

### Available Fixture Cases

| Case ID | Description |
|---------|-------------|
| `DSP-000045` | Resolved route-deviation case, `synthetic_reasoning: false` |
| `DSP-000046` | Same case with `synthetic_reasoning: true` (tests the badge) |
| `DSP-000047` | Escalated case with human-review summary |
| `DSP-000048` | No-show case (different category) |
| `DSP-000049` | Unsupported-for-automation category routed to human review |
| `DSP-000050` | Triggers a `database_unavailable` (503) error |
| `DSP-000999` | Triggers a `not_found` (404) error |

## Architecture

### Type Generation

Types are generated from `shared/openapi.yaml` using `openapi-typescript`:

```bash
npm run generate-types
```

The generated file is `src/lib/api/generated.ts`. Type aliases are re-exported
from `src/lib/api/types.ts`. **Never hand-write types.** If a generated type
disagrees with the backend, that is a contract issue to raise with the lead
agent — never widen a type to make a component compile.

### Money

Money is an integer of cents plus a currency code. The `formatMoney` helper
in `src/lib/api/money.ts` is the **single place** where cents are converted
to a display string. It uses `Intl.NumberFormat('en-SG', { style: 'currency',
currency })` per the contract.

- 325 SGD → `S$3.25` (or `$3.25` on runtimes with limited ICU data)
- Never parse a float, never do arithmetic on a display string.

### Deterministic Reasoning Badge

When `synthetic_reasoning: true` on a `CaseResult`, a visible badge appears. The flag means a scripted
fallback produced the reasoning rather than an LLM. It describes how ruling text was produced; it is
separate from the `synthetic` record-provenance flag. Company-imported and generated records use the same
display and adjudication behavior.

### Categories and Human Review

The closed filing categories are `route_deviation`, `fare_calculation`, `no_show_charge`,
`other_cancellation_fee`, `property_damage`, `safety_incident`, `lost_item`, and `conduct_complaint`.
Categories without automated adjudication support are filed and shown as pending human review. The
frontend displays the status and review summary returned by the API.

### Confidence

Confidence is displayed as a percentage to one decimal (`0.842` → `84.2%`).
The raw float is available in the `aria-label`. The escalation state is
**never** derived by comparing confidence to a threshold — it branches only
on `judge.escalation.escalated`, which is authoritative.

### State Surfaces

Loading, empty, error, and escalated are first-class render paths:
- **Loading**: skeleton with `aria-busy`
- **Empty**: "Case Not Found" with the case ID
- **Error**: distinguishes `database_unavailable` (503) from `internal_error` (500)
- **Escalated**: escalation panel with reasons and human-review summary

### Evidence Controls

Each evidence reference is a clickable, keyboard-accessible disclosure that
fetches `GET /evidence/{evidence_id}` on demand and reveals the full Evidence
record. Each evidence item shows its verification status and uncertainty
percentage, including the case where `uncertainty_pct` is absent.

### Reviewer workflow

The root page shows filing-date metrics, charts, and a filterable case list using the
`/metrics/*` and `/disputes` endpoints. Selecting a case opens `/cases/[caseId]`.
Live cases can be approved or overridden there; historical cases show recorded rulings
read-only. The fixture client and `src/fixtures/` provide synthetic responses when no API
base URL is configured.

## Testing

```bash
npm test           # run once
npm run test:watch # watch mode
```

Test suite covers:
- Money formatting (cents → display, no floats)
- Synthetic badge (both states)
- Confidence formatting (including the 0.6996 hazard)
- Unknown enum fallback (safe rendering)
- Case view (loads from fixture, all sections present)
- State surfaces (loading, empty, database_unavailable, escalated)
- Evidence controls (reveal, verification, uncertainty absent, keyboard)
- Source scan (no database, no SQL, no credentials in source)

## Integrity Rules

- **I-6**: `synthetic_reasoning: true` → visible badge. Tested in both states.
- No database connections, no SQL, no credentials in the frontend source.
- No ruling, confidence, urgency, or deviation is computed in the browser.
- Fixtures live in a fixture layer and are visibly labelled.

## Screenshots

All screenshots captured from live backend integration.

| Screenshot | State | File |
|---|---|---|
| Escalated case | Loaded, escalated, synthetic badge | screenshots/01-escalated-case-full.png |
| Resolved case | Loaded, resolved, no-show refund | screenshots/02-resolved-case.png |
| Expanded evidence | Evidence control expanded | screenshots/03-expanded-evidence.png |
| Error state | Backend stopped | screenshots/04-error-state.png |
| Empty state | Case not found | screenshots/05-empty-state.png |
| Escalated no-show | Loaded, escalated, no-show | screenshots/06-escalated-no-show.png |
| Direct CORS (no proxy) | Loaded via direct cross-origin call to :8000 | screenshots/07-direct-cors-no-proxy.png |

## Live Integration Report

Contract defects found against shared/openapi.yaml:

1. ~~Citation `valid` field missing~~ — **FIXED** in PR #20. `valid` is now required in the schema.
2. `invalid_citation_rate` not in schema — Backend sends this field; not in OpenAPI spec.
3. Evidence IDs like EV-000123-1 do not match ^EV-\d{6}$ pattern.
4. ~~POST /disputes expects `subject` field not documented~~ — **FIXED** in PR #20. `subject` added to `FileDisputeRequest` schema.
5. ~~Backend lacks CORS headers~~ — **FIXED** in PR #23. CORS headers now allow `http://localhost:3000`. Next.js rewrites proxy removed in this PR.
