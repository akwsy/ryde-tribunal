# Policy fixture — TEST DOUBLE ONLY

`ryde-policy-0.1.0.json` in this directory is a **test double**, NOT the runtime source of
truth. The canonical, authoritative policy file is
`database/seed/policy/ryde-policy-0.1.0.json` (D-18), owned by the database specialist and
consumed UNCHANGED by `app/policy/loader.py`.

The loader uses this fixture **only** as a fallback when the canonical file is absent — e.g. an
isolated checkout that does not include the `database/` tree. Its rule TEXT is the fuller prose
from `docs/03-mock-policy.md` and DIVERGES from the canonical file, which carries the operative
first sentence of each rule (see `backend/ASSUMPTIONS.md` A-1). Do not treat this file as the
policy the Judge reasons over in a real run — that is always the canonical file.
