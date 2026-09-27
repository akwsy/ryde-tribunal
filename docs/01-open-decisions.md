# 01 — Open decisions

Each item carries a **recommendation** I will proceed on if approved, and a **blocking** flag.
This is the historical decision register. Current behavior is described in the component READMEs,
`shared/openapi.yaml`, and the latest entries of `docs/05-integration-log.md`.
Blocking items stopped Phase Zero work in the named component until the owner ruled. Non-blocking items
are implemented behind a documented seam so reversing them is cheap.

| id | decision | recommendation | blocking |
|---|---|---|---|
| D-01 | Backend framework | FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic, managed by `uv` | yes — backend |
| D-02 | Frontend framework | Next.js 15 (App Router) + TypeScript + Tailwind + Recharts | yes — frontend |
| D-03 | Python version | 3.12 pinned via `uv` (3.14.7 is the system default here; too new for parts of this stack) | yes — backend |
| D-04 | LLM provider | provider-agnostic `ModelProvider` interface; `openai-compatible` adapter + a `deterministic-mock` adapter for tests. Owner supplies base URL, model name, and key at approval time. **Closed for Phase Zero by project-owner sign-off on 2026-09-25.** The configured Gemini request failed and deterministic fallback completed the case; this meets the owner's Phase Zero evaluation-success definition. A successful live-LLM case-specific run remains a Phase One evaluation target, not a Phase Zero blocker. | resolved |
| D-05 | "Model memory" scope | **case persistence** for Phase Zero (all model work durable and retrievable); conversational memory deferred to Phase One | no |
| D-06 | Data retention / deletion | owner-authorized company test records may be imported into the local database alongside synthetic records; no deletion/retention policy implemented; `DELETE /cases/{id}` deferred | no |
| D-07 | Auth / authz | No user authentication for the local reviewer app through Phase One. Keep the single local reviewer identity/header for mutation audit fields; do not add login screens. | resolved |
| D-08 | Confidence format | float `0.000`–`1.000`, 3 decimals | no |
| D-09 | Escalation threshold | `< 0.70` escalates. Configurable, recorded on every ruling | no |
| D-10 | High impact definition | monetary effect ≥ SGD 25.00; a `safety_incident` that does not pass the verified decisive-fact eligibility gate; or ≥3 disputes by the same party in 30 days. Fraud risk influences the Judge's ruling but is not itself an escalation trigger. Effective policy: `ryde-policy-0.1.2`. | resolved |
| D-11 | Ruling limits | refund ≤ the disputed fare component; compensation ≤ `$15.00` goodwill; anything above either cap escalates rather than auto-resolving | no |
| D-12 | Node.js toolchain | **Resolved on 2026-09-25** — Node.js 20.20.2 and npm 10.8.2 are available on the project Mac. | resolved |
| D-13 | Postgres provisioning | use the running local Postgres 16.15 on `:5432`, database `ryde_tribunal`; no Docker on this machine | no |
| D-14 | Dispute categories in Phase Zero | filing vocabulary: `route_deviation`, `no_show_charge`, `fare_calculation`, `other_cancellation_fee`, `property_damage`, `safety_incident`, `lost_item`, `conduct_complaint`; only the first two have automated policy flows, other approved categories go to human review | no |
| D-15 | Phase One "80% complete" | **feature completeness** against the §3 checklist — every listed control present and wired to a real API response — with visual polish explicitly out of scope | resolved |
| D-16 | Image analysis in Phase One | out of scope; `property_damage` evidence stores image metadata and a stub verification status only | no |
| D-17 | Deployment | local development only through Phase One; no deployment target chosen | no |
| D-18 | Policy source of truth | Versioned policy JSON under `database/seed/policy/`, loaded at runtime. The effective policy is `ryde-policy-0.1.2`; historical versions remain immutable. No policy constants duplicated in Python source. | resolved |
| D-19 | GitHub repository | **DONE** — `akwsy/ryde-tribunal`, private, `main` pushed at `a6552f9` | resolved |
| D-20 | Branch protection on `main` | **NOT POSSIBLE** on this plan. Classic protection and repository rulesets both return `403 Upgrade to GitHub Pro or make this repository public`. Options: make the repo public, upgrade to Pro, or accept the CI guards as the only gate. Pending owner choice | yes — see note |
| D-21 | Python toolchain | **DONE** — Python 3.12.14 installed via `uv`, project pinned in `.python-version` | resolved |
| D-22 | Historical archive ruling pairs | Existing archive decisions retain their recorded origin and human-review state. Should archive cases with only a final decision gain a separate reconstructed model-proposed ruling, or should paired proposed/approved rulings apply only to cases processed by this app? No reconstructed proposal has been created | no — clarify before changing archive history |

## Notes on the consequential ones

**D-04 (closed).** The handoff allows external LLM calls but forbids assuming a provider. The seam is the
decision that matters, not the vendor: `ModelProvider.complete(prompt, schema) -> structured` with
per-component provider metadata on the output (integrity rule I-6). A `deterministic-mock` adapter is
required so the test suite runs offline, and it must be labelled as scripted in every payload. The
project owner signed off Phase Zero on 2026-09-25 after the configured Gemini request failed and
deterministic fallback completed the case. This closes the Phase Zero provider decision under the owner's
stated acceptance rule. Live-model reasoning quality remains to be evaluated in Phase One; the sign-off
does not claim a successful LLM-generated ruling.

**D-07.** Flagged blocking deliberately. Deferring auth entirely tends to produce a fully
unauthenticated mutation surface that then ships; a header-based reviewer identity costs almost nothing
now and leaves a real seam for Phase One.

**D-12 (resolved).** The project Mac now has Node.js 20.20.2 and npm 10.8.2 available.

**D-18.** Policy duplicated between a JSON file and hardcoded constants drifts, and the copy the tests
exercise stops being the copy the documentation describes. One loader, one file, version on every ruling.

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
