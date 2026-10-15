# Contributor notes

- Keep the local database intact. Database tests must use disposable databases ending in `_test` or `_tests`.
- Keep credentials, company exports, case review labels, generated datasets, and model checkpoints out of Git.
- New filings use the configured versioned Ryde policy. Preserve historical policy versions for recorded decisions and keep Tribunal operating safeguards clearly distinguished from Ryde policy.
- Keep model proposals, deterministic fallback output, and human decisions distinct. Do not promote unreviewed model output into training data.
- `shared/openapi.yaml` is the API contract. Regenerate frontend types when it changes.
- Run the affected component checks and the full relevant suite before committing.
