# Ryde Tribunal — Frontend

Phase Zero case view for the Ryde Tribunal dispute-resolution system.

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

Open [http://localhost:3000](http://localhost:3000) — redirects to `/cases/DSP-000045`.

## Fixture Mode

When `NEXT_PUBLIC_API_BASE_URL` is not set, the app runs in **fixture mode**.
All data is synthetic and visibly labelled as "FIXTURE — not production data."
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

### Synthetic Reasoning Badge

When `synthetic_reasoning: true` on a `CaseResult`, a visible badge appears.
The flag means a scripted fallback produced the text rather than a model.
The badge appears at the case level, in each advocate panel, and in the
judge ruling.

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

### Phase One Extension

The architecture is structured so Phase One is an extension, not a rewrite:
- The typed API client already has methods for `/metrics/overview`,
  `/metrics/timeseries`, `/disputes` (list), `/disputes/{id}/approve`,
  `/disputes/{id}/override`.
- The case view route at `/cases/[caseId]` stays as-is.
- A dashboard route at `/dashboard` can be added without touching the case view.
- Fixtures for Phase One data (case summary page, metrics, timeseries) are
  already in `src/fixtures/`.

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

## Live Integration Report

Contract defects found against shared/openapi.yaml:

1. Citation `valid` field missing — Backend omits required `valid: boolean` from citations. UI renders (invalid) as safe fallback.
2. `invalid_citation_rate` not in schema — Backend sends this field; not in OpenAPI spec.
3. Evidence IDs like EV-000123-1 do not match ^EV-\d{6}$ pattern.
4. POST /disputes expects `subject` field not documented in FileDisputeRequest schema.
5. Backend lacks CORS headers — browser requests from localhost:3000 to localhost:8000 are blocked. Worked around with Next.js rewrites proxy.
