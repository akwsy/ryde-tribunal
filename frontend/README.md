# Frontend

Next.js reviewer interface for Ryde Tribunal, a tool for reviewing ride disputes, evidence, Ryde policy, and proposed decisions. The public site is [ryde-tribunal.vercel.app](https://ryde-tribunal.vercel.app/). Guest profiles are synthetic and read-only. The Vercel frontend currently loads, while the online case archive still depends on the Render database configuration described in [hosted demo status and setup](../docs/07-hosted-demo.md).

For local setup, see the root [README](../README.md) and run `./run-local.sh` from the repository root to start the complete app against its existing local database.

## API and types

[`shared/openapi.yaml`](../shared/openapi.yaml) is authoritative. Runtime requests use
`openapi-fetch` in `src/lib/api/client.ts`, and generated types live in `src/lib/api/generated.ts`.
After changing the contract, run:

```bash
npm run generate-types
npx tsc --noEmit
```

The dashboard lists all filing dates with search, category/status filters, and pagination; chart
metrics use their own selected date range. Historical decisions appear read-only with their
recorded policy version. New cases are reviewed through the same interface.

Evidence cards show the claim and a readable description. **View evidence** opens the exact cited
record in a movable desktop panel or mobile sheet. The source field, verification status, and
provenance remain visible, while raw values are under Technical details. GPS maps load only when a
location record is opened and include OpenStreetMap attribution; text remains available when
coordinates or map tiles are unavailable.

The `synthetic_reasoning` flag identifies deterministic model output. It is separate from the
record's data provenance. No decision, amount, confidence, or route measurement is computed in the
browser.

## Development checks

```bash
npm test
npm run build
npx tsc --noEmit
```

The tests cover API request construction, all-date search, case outcomes, evidence opening and
keyboard dismissal, responsive page content, citations, and loading/error states. The local
browser walkthrough should also be checked at 390, 768, and 1440 pixels.
