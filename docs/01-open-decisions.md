# 01 — Open decisions

This is a historical decision register. Current behavior is described in the root README,
`shared/openapi.yaml`, the current Ryde policy JSON, and `docs/submission/READINESS.md`.

| id | decision | recommendation | blocking |
|---|---|---|---|
| D-01 | Backend framework | FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic, managed by `uv` | yes — backend |
| D-02 | Frontend framework | Next.js 15 (App Router) + TypeScript + Tailwind + Recharts | yes — frontend |
| D-03 | Python version | 3.12 pinned via `uv` (3.14.7 is the system default here; too new for parts of this stack) | yes — backend |
| D-04 | LLM provider | Keep a provider-agnostic `ModelProvider` interface and deterministic fallback. A successful live-model run for both core categories is a release gate and remains unverified. | open |
| D-05 | "Model memory" scope | **case persistence** for Phase Zero (all model work durable and retrievable); conversational memory deferred to Phase One | no |
| D-06 | Data retention / deletion | owner-authorized company test records may be imported into the local database alongside synthetic records; no deletion/retention policy implemented; `DELETE /cases/{id}` deferred | no |
| D-07 | Auth / authz | No user authentication for the local reviewer app through Phase One. Keep the single local reviewer identity/header for mutation audit fields; do not add login screens. | resolved |
| D-08 | Confidence format | float `0.000`–`1.000`, 3 decimals | no |
| D-09 | Escalation threshold | `< 0.70` escalates. Configurable, recorded on every ruling | no |
| D-10 | High impact definition | Apply published Ryde rules and separately labelled Tribunal operating safeguards. Current rule text is versioned in `ryde-policy-1.0.0`; unsupported or uncertain outcomes require review. | resolved |
| D-11 | Ruling limits | refund ≤ the disputed fare component; compensation ≤ `$15.00` goodwill; anything above either cap escalates rather than auto-resolving | no |
| D-12 | Node.js toolchain | **Resolved on 2026-09-25** — Node.js 20.20.2 and npm 10.8.2 are available on the project Mac. | resolved |
| D-13 | Postgres provisioning | use the running local Postgres 16.15 on `:5432`, database `ryde_tribunal`; no Docker on this machine | no |
| D-14 | Dispute categories | Route deviation and no-show charge are the core adjudication categories. Other filing categories use explicit review paths until policy support is verified. | resolved |
| D-15 | Phase One "80% complete" | **feature completeness** against the §3 checklist — every listed control present and wired to a real API response — with visual polish explicitly out of scope | resolved |
| D-16 | Image analysis in Phase One | out of scope; `property_damage` evidence stores image metadata and a stub verification status only | no |
| D-17 | Deployment | local development only through Phase One; no deployment target chosen | no |
| D-18 | Policy source of truth | Versioned JSON under `database/seed/policy/`, loaded at runtime. New cases use source-backed `ryde-policy-1.0.0`; earlier policy snapshots and decisions remain immutable. | resolved |
| D-19 | GitHub repository | **DONE** — `akwsy/ryde-tribunal`, private, `main` pushed at `a6552f9` | resolved |
| D-20 | Branch protection on `main` | **NOT POSSIBLE** on this plan. Classic protection and repository rulesets both return `403 Upgrade to GitHub Pro or make this repository public`. Options: make the repo public, upgrade to Pro, or accept the CI guards as the only gate. Pending owner choice | yes — see note |
| D-21 | Python toolchain | **DONE** — Python 3.12.14 installed via `uv`, project pinned in `.python-version` | resolved |
| D-22 | Historical archive ruling pairs | Preserve the rulings as recorded. Do not reconstruct missing proposals or imply that historical cases were processed by this app. | resolved |

## Notes on the consequential ones

**D-04.** Deterministic fallback supports local development and tests, but does not count as a live
provider demonstration. Keep provider identity and fallback reason visible in traces and readiness
results. The live provider gate remains open until both core categories complete without fallback.

**D-07.** Flagged blocking deliberately. Deferring auth entirely tends to produce a fully
unauthenticated mutation surface that then ships; a header-based reviewer identity costs almost nothing
now and leaves a real seam for Phase One.

**D-12 (resolved).** The project Mac now has Node.js 20.20.2 and npm 10.8.2 available.

**D-18.** New cases use `ryde-policy-1.0.0`. The older `0.1.x` policy files are retained only to explain
historical records and compatibility tests; they do not govern new decisions.

**D-19 / D-20.** The owner's rule is that every specialist pushes to GitHub when its changes are done and
holds at most one branch at a time. That rule cannot be followed without a remote, so the repository was
blocking. `akwsy/ryde-tribunal` now exists, private, with `main` pushed.

Branch protection, however, **could not be applied**. Both the classic
`PUT /repos/:owner/:repo/branches/main/protection` and the newer
`POST /repos/:owner/:repo/rulesets` return `403 Upgrade to GitHub Pro or make this repository public`.
Protecting a branch on a **private** repository is a paid feature on GitHub Free. Three ways forward:

1. **Make the repository public.** Protection becomes free immediately. Defensible here — everything in
   this repo is synthetic data, a fictional company policy, and documentation. Nothing confidential.
2. **Upgrade to GitHub Pro.** Keeps it private and enables protection.
3. **Accept the CI guards as the only gate.** `guards` still runs on every pull request, so an
   ownership or one-branch violation is still caught and still visible. What is missing is *prevention*:
   nothing stops a direct push to `main`, and nothing forces a PR to be green before merge.

Interim mitigation while this is undecided: every specialist prompt and every brief states that pushing
to `main` is forbidden and that merges are the lead agent's, and the lead agent checks the `guards`
result before merging. That is convention, not enforcement — a specialist that ignores it will succeed
technically and be caught after the fact.
