# Policy fixture — TEST DOUBLE ONLY

`ryde-policy-0.1.0.json` is a retained historical test double. Current backend tests read
the canonical `database/seed/policy/ryde-policy-0.1.2.json` directly. The loader no longer
falls back to a policy fixture when that canonical file is missing.

The old QA fixtures explicitly select this file to exercise historical behavior. Its rule
text differs from the canonical file; it is not a fallback or a source for current rulings.
