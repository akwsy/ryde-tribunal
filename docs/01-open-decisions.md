# 01 — Open decisions

Each item carries a **recommendation** I will proceed on if approved, and a **blocking** flag.
Blocking items stop Phase Zero work in the named component until the owner rules. Non-blocking items
are implemented behind a documented seam so reversing them is cheap.

| id | decision | recommendation | blocking |
|---|---|---|---|
| D-01 | Backend framework | FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic, managed by `uv` | yes — backend |
| D-02 | Frontend framework | Next.js 15 (App Router) + TypeScript + Tailwind + Recharts | yes — frontend |
| D-03 | Python version | 3.12 pinned via `uv` (3.14.7 is the system default here; too new for parts of this stack) | yes — backend |
| D-04 | LLM provider | provider-agnostic `ModelProvider` interface; `openai-compatible` adapter + a `deterministic-mock` adapter for tests. Owner supplies base URL, model name, and key at approval time | yes — backend |
| D-05 | "Model memory" scope | **case persistence** for Phase Zero (all model work durable and retrievable); conversational memory deferred to Phase One | no |
| D-06 | Data retention / deletion | synthetic-only, no retention policy implemented; `DELETE /cases/{id}` deferred | no |
| D-07 | Auth / authz | Phase Zero: single hardcoded reviewer identity via `X-Reviewer-Id` header, **and every mutating route guarded by it from the first commit** — an unauthenticated write surface is not an acceptable interim state. Real auth is Phase One | yes — backend |
| D-08 | Confidence format | float `0.000`–`1.000`, 3 decimals | no |
| D-09 | Escalation threshold | `< 0.70` escalates. Configurable, recorded on every ruling | no |
| D-10 | High impact definition | any of: monetary effect ≥ `$25.00`; category `safety_incident`; fraud risk ≥ `0.60`; disputant with ≥3 disputes in 30 days | no |
| D-11 | Ruling limits | refund ≤ the disputed fare component; compensation ≤ `$15.00` goodwill; anything above either cap escalates rather than auto-resolving | no |
| D-12 | **Node.js is not installed on this machine** | install Node 20 LTS via Homebrew before the frontend brief is dispatched — otherwise the frontend specialist cannot run, test, or verify anything | yes — frontend |
| D-13 | Postgres provisioning | use the running local Postgres 16.15 on `:5432`, database `ryde_tribunal`; no Docker on this machine | no |
| D-14 | Dispute categories in Phase Zero | `route_deviation` and `no_show` end to end (the handoff's minimum); `property_damage` and `safety_incident` schema-supported, adjudication in Phase One | no |
| D-15 | Phase One "80% complete" | **feature completeness** against the §3 checklist — every listed control present and wired to a real API response — with visual polish explicitly out of scope | no, decide before Phase One |
| D-16 | Image analysis in Phase One | out of scope; `property_damage` evidence stores image metadata and a stub verification status only | no |
| D-17 | Deployment | local development only through Phase One; no deployment target chosen | no |
| D-18 | Policy source of truth | policy lives in **one** place: `database/seed/policy/ryde-policy-0.1.0.json`, loaded at runtime and versioned. No policy constants duplicated in Python source | no |
| D-19 | GitHub repository | create `akwsy/ryde-tribunal`, **private**, `main` as default branch. `gh` is authenticated as `akwsy` with `repo` scope. Needed before any specialist can push | yes — all three |
| D-20 | Branch protection on `main` | require a pull request, require the `guards` CI check to pass, block force-push and deletion. Self-review by the author is not sufficient — the lead agent merges | yes — all three |

## Notes on the consequential ones

**D-04.** The handoff allows external LLM calls but forbids assuming a provider. The seam is the
decision that matters, not the vendor: `ModelProvider.complete(prompt, schema) -> structured` with
per-component provider metadata on the output (integrity rule I-6). A `deterministic-mock` adapter is
required so the test suite runs offline, and it must be labelled as scripted in every payload — a
scripted provider quietly presented as an agent is the single most likely way this project ends up
"working" without meeting its own mission.

**D-07.** Flagged blocking deliberately. Deferring auth entirely tends to produce a fully
unauthenticated mutation surface that then ships; a header-based reviewer identity costs almost nothing
now and leaves a real seam for Phase One.

**D-12.** Hard blocker, not a preference. There is no `node`, `npm`, or `pnpm` on this machine.

**D-18.** Policy duplicated between a JSON file and hardcoded constants drifts, and the copy the tests
exercise stops being the copy the documentation describes. One loader, one file, version on every ruling.

**D-19 / D-20.** The owner's rule is that every specialist pushes to GitHub when its changes are done and
holds at most one branch at a time. That rule cannot be followed without a remote, so the repository and
its branch protection are blocking for all three specialists rather than housekeeping. Private is the
recommendation because the repository carries a fictional company's policy document and a synthetic data
generator, neither of which benefits from being public, and making it public later is one click while
un-publishing is not. Creating a repository under your account is an external action on a shared system,
so I have not done it — say the word and it takes one command.
