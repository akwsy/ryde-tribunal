# Frontend assumptions — historical implementation record

This file records Phase Zero development decisions. Use `frontend/README.md` for current
routes and setup; references below to missing handoff files or a future dashboard describe
the state when the decisions were written.

Record of every assumption made during Phase Zero development. Where the
requirements were ambiguous and the behaviour was material, these were
raised with the lead agent before proceeding.

## A-1: Currency symbol for SGD

**Date**: 2026-09-22
**Resolved**: Confirmed by lead agent (Q4 response).

The contract uses `Intl.NumberFormat('en-SG', { style: 'currency', currency })`.
On runtimes with full `en-SG` ICU data, this produces `S$3.25`. On Node.js
with ICU 78.x (used in this dev environment), the symbol may render as `$3.25`
because the `en-SG` locale data for the `$` → `S$` mapping is not included.

**Decision**: Use the contract-specified formatter. The symbol is a
locale-data concern, not a code concern. The amount (3.25) is always correct.
Tests verify the amount, not the symbol, to remain locale-data-independent.

## A-2: Backend handoff sample files

**Date**: 2026-09-22
**Resolved**: Lead agent said files would be at
`backend/handoff/sample_case_result_route_deviation.json` and
`sample_case_result_no_show.json`.

As of commit 4485d78, the `backend/handoff/` directory does not exist on
`main`. The fixtures in `src/fixtures/` were transcribed directly from
`docs/02-api-contract.md` §3-4 and the OpenAPI schemas in
`shared/openapi.yaml`. When the backend sample files become available, the
fixtures should be reconciled against them.

## A-3: Next.js security advisories

**Date**: 2026-09-22
**Status**: Noted, not blocking.

`npm audit` reports CVEs in `next@15.5.4` (SSRF via image optimization,
middleware bypass). The patched backport is `15.5.25`. Attempts to install
`15.5.25` were blocked by a stuck temp directory in `node_modules`
(`.next-QxM8Ghkf`), which appears to be a safe-delete shim. Phase Zero does
not use image optimization, server actions with untrusted input, or
middleware proxy, so the CVEs are not exploitable in this phase. Upgrading
to `15.5.25` should be done before Phase One.

## A-4: No live backend available

**Date**: 2026-09-22
**Resolved**: Confirmed by lead agent (Q2 response).

No backend is deployed. The app runs in fixture mode. The client is
structured so that repointing `NEXT_PUBLIC_API_BASE_URL` is the only change
needed. Verifying against a live backend is a lead-run integration step.

## A-5: Confidence display — percentage with one decimal

**Date**: 2026-09-22
**Resolved**: Confirmed by lead agent (Q3 response).

Confidence is displayed as a percentage to one decimal (`0.842` → `84.2%`).
The raw float is in the `aria-label`. Escalation is never derived by
comparing confidence to a threshold — it branches only on
`judge.escalation.escalated`.

## A-6: Unknown enum values render a safe fallback

**Date**: 2026-09-22
**Status**: Assumed (not raised — behaviour is clear from the contract).

When the API returns an enum value not in the known set (e.g., a new
`ruling_type` added before the frontend is updated), the UI renders a safe
fallback string ("Unknown ruling type: X") rather than throwing. This is
tested in `tests/unknown-enum.test.ts`.

## A-7: `case_facts` and `measurements` are free-form objects

**Date**: 2026-09-22
**Status**: Assumed from the OpenAPI schema.

The contract defines `case_facts` and `measurements` as objects with
category-specific fields (different for `route_deviation` vs `no_show_charge`).
The frontend renders them generically (as a JSON view in a `<details>`
for `case_facts`, and as a key-value grid for `measurements`) rather than
hardcoding specific field shapes. This is because the fields vary by
category and the contract does not enumerate every variant.

## A-8: `provider.kind` field name

**Date**: 2026-09-22
**Status**: Assumed from the OpenAPI schema.

The OpenAPI spec uses `kind` for the provider type discriminator (not
`type` or `provider_type`). The enum values are `llm` and
`deterministic-mock`. The deterministic-reasoning badge is shown when either
`caseResult.synthetic_reasoning` is true OR `provider.kind` is
`deterministic-mock`. It describes how reasoning was produced, not whether
the underlying record came from generated seed data or a company import.

## A-9: `ExternalFinding` shape

**Date**: 2026-09-22
**Status**: Assumed from the OpenAPI schema.

The contract's `external_findings` array contains objects with `summary`,
`source_url`, `reliability`, and `evaluation` fields. The frontend renders
these as a list with the summary, a link to the source URL, and the
reliability/evaluation annotations. If the backend returns a different
shape, this is a contract issue.

## Submission polish
Contract types generated from approved v0.5.0. Recorded examples remain visibly labelled;
historical policy links refuse a mismatched version. Trace events are read from API data only.
No new dependency. CodeBuddy/WorkBuddy follow-up tasks remain separately documented by the lead.
