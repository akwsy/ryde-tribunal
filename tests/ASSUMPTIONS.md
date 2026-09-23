# QA assumptions

- The public API is the integration boundary; tests do not import orchestration functions.
- Phase Zero's offline acceptance run uses deterministic mock output and therefore asserts the
  `synthetic_reasoning` contract, not real-provider language quality.
- The supplied seeded IDs are represented by independent QA records in offline tests. PostgreSQL
  seeded execution is an additional environment gate and must use the documented read-only role.
- Malformed-evidence coverage is expected to be expanded once the backend exposes a public filing
  path for malformed persisted evidence; the current attachment API validates only transport shape.
