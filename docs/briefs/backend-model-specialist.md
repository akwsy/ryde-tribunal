# Brief — Backend / model specialist

Phase Zero. Read `docs/00-ownership.md`, all of `docs/02-api-contract.md`, `docs/03-mock-policy.md`, and
**all of `docs/04-integrity-rules.md`** before writing anything. The integrity rules are the acceptance
bar for this brief, not advice.

## 1. Mission and scope

Build the dispute-processing backend: the HTTP API, the orchestration, the three model components
(Rider Advocate, Driver Advocate, Judge), policy loading, evidence handling, persistence of model work,
escalation, and the reviewer approve/override flow.

The defining requirement: **the three components must reason from the individual case.** The workflow
around them may be deterministic; their conclusions may not be. A rules engine that computes the answer
and a language model that restates it does not satisfy this brief even if every endpoint returns 200.

## 2. Non-goals

- You do not write migrations or seed data **for the data layer**. You read `ride_data` and
  `case_archive` through the eight read-only accessors, and your database role has `SELECT` only on them —
  an attempted write fails at PostgreSQL, by design.
- You **do** own the `tribunal` schema and its own migration set under `backend/`, covering `case_*`,
  `model_work_*`, `ruling_*`, `case_history`, and `idempotency_keys`. You persist advocate and Judge work
  yourself; there is no `persist_model_work` accessor (it was removed from contract draft v0.1.0 as a
  write function wrongly placed in a read contract).
- You do not build UI.
- You do not change the HTTP contract. If it is wrong, raise it.
- You do not implement Phase One components (Fraud model, Policy/Precedent RAG, Evidence Collection
  agent). Leave named seams, no implementations.
- You do not implement real auth (D-07 scopes Phase Zero to a reviewer-id header).

## 3. Allowed paths

`backend/**` — `backend/app/` (`api/`, `orchestration/`, `models/` for advocates+judge, `policy/`,
`evidence/`, `providers/`, `persistence/`), `backend/tests/`, `backend/README.md`,
`backend/ASSUMPTIONS.md`, `backend/pyproject.toml`.

## 4. Forbidden paths

`database/**`, `frontend/**`, `shared/**`, `docs/**`, `tests/**`, `README.md`, `.env.example`.

## 5. Contracts

**Input:** the eight read-only database accessors (`docs/02-api-contract.md` §5); the policy JSON at
`database/seed/policy/ryde-policy-0.1.0.json`; `docs/03-mock-policy.md` as the prose the Judge reasons
over.

**Output:** exactly the endpoints and payloads in `docs/02-api-contract.md` §2–4. `CaseResult` is
complete on every response — no field silently omitted.

**Internal seams you must build:**

- `ModelProvider.complete(prompt, response_schema) -> structured` with two adapters:
  `openai_compatible` and `deterministic_mock`. Selected by env; the mock is what CI uses.
  Both stamp `provider: {kind, model}` onto every component output (I-6).
- `PolicyContext` — a frozen structure carrying applicable rule ids, rule text, and **factual
  measurements only**. It must be structurally incapable of carrying a ruling, an action, an amount, or a
  fault attribution (I-1).
- `CitationValidator` — the six semantic checks in I-3.
- `EvidencePrecedence` — the verified-over-unverified rule in I-7, applied per factual question.
- `ExternalFindings` — quarantined external information per I-8.

## 6. Dependencies and assumptions

*Given:* FastAPI + Pydantic v2 + SQLAlchemy 2.0 (D-01), Python 3.12 via `uv` (D-03), provider config
supplied by the owner at approval (D-04), reviewer-id header auth (D-07), confidence `0.000–1.000`
(D-08), escalation below `0.70` (D-09), high impact per D-10, ruling caps per D-11, categories
`route_deviation` + `no_show` end to end (D-14).

*Record in `backend/ASSUMPTIONS.md`:* prompt structure, how each advocate is restricted to
evidence its party may see (`Evidence.visibility`), how you keep the two advocates from sharing state,
and your similarity ceiling for the I-5 test with the reasoning behind the number.

*Ambiguous → ask:* anything that would require you to hardcode a category-level conclusion.

## 7. Required tests

Contract and flow:

- A dispute can be filed and adjudicated through the documented API.
- Both advocates retrieve relevant evidence from the database and return case-specific arguments with
  evidence **and** policy references.
- The Judge receives both advocate outputs plus the underlying case context, and returns ruling type,
  recommended action, confidence, reasoning, evidence references, policy references, and escalation
  state.
- `route_deviation` and `no_show` both produce valid end-to-end results.
- Model work is persisted and retrievable after the request completes.
- The policy version used is recorded on every ruling, and `GET /policy/{version}` returns the document
  actually loaded.
- `POST /approve` and `POST /override` append to `case_history` without destroying the original ruling;
  override `reason_code` outside the closed vocabulary is rejected.
- Idempotency is **concurrency-safe**: two simultaneous adjudications with the same key produce one
  ruling. Test it with real concurrency, not sequential calls.

Integrity (each maps to a rule in `docs/04-integrity-rules.md`):

- **I-1** `PolicyContext` carries no verdict-shaped field; a static check enforces it.
- **I-3** an advocate citing a real same-case record whose stored value contradicts the claim is marked
  `invalid_citation`.
- **I-5** ≥6 materially different cases per category yield pairwise-distinct normalized arguments and
  distinct cited-evidence sets.
- **I-6** `provider` is present on every component output; `synthetic_reasoning` is true whenever any
  component ran on the mock.
- **I-7** an appeal where unverified chat contradicts verified GPS does not flip the ruling — it holds or
  escalates.
- **I-8** with the external provider forced to fail, a ruling still returns, `external_findings` is
  empty, `external_unavailable` is true, and nothing is fabricated.

Failure and escalation:

- Contradictory or missing evidence → uncertain or escalated, never a confident ruling.
- High-impact or below-threshold case → escalated with a complete human-review summary (RP-ESC-005).
- A `safety_incident` is escalated regardless of confidence (RP-SAFETY-001).
- Database unavailable → `database_unavailable` error, **no** ruling.
- A malformed evidence record surfaces as uncertainty, not as fact.
- Every mutating route rejects a request with no `X-Reviewer-Id`.

## 8. Passing criteria

All §7 tests pass on the `deterministic_mock` provider offline, and the flow tests pass again against a
real provider once the owner supplies credentials. The integrity tests must fail if someone reintroduces
a precomputed verdict — verify that by trying it locally and confirming red.

## 9. Handoff artifacts

`backend/README.md` (setup, env vars, run, test, how to switch providers), `backend/ASSUMPTIONS.md`, a
generated OpenAPI document for lead-agent diff against `shared/openapi.yaml`, a `pytest` log, a sample
`CaseResult` per category committed as a fixture, and a pinned dependency list. Report to the lead agent.

## 10. Git and GitHub

Read `docs/06-git-workflow.md` in full. It is binding. The owner-set rules that apply to you:

- **Your branch prefix is `be/`.** Branch from `main`, never from another specialist's branch.
- **You hold at most one branch at a time** — one in existence, not one in progress. Your previous
  branch must be merged and deleted on the remote *and* locally before you cut the next one. No second
  branch to park work or try an alternative approach; this matters especially here, because the
  orchestration invites parallel experiments. If the work does not fit one branch, say so and the section
  gets split.
- **Push to GitHub when you are done with your changes**, then open a pull request against `main`. A push
  is a claim the work is done, so `bash tools/ci/check-ownership.sh`, `bash tools/ci/check-secrets.sh`,
  `bash tools/ci/check-one-branch.sh` and your §7 suite — including every integrity test — must be green
  first. Pushing with a red integrity test is a process violation even if the code is fixed later.
- Address review feedback on the **same** branch. Never force-push a branch under review.
- After the lead agent squash-merges, delete the branch to free your slot.
- You do not merge your own pull request.

Your diff must stay inside `backend/`. In particular you may not commit a migration, a seed file, or a
change to `shared/openapi.yaml` — generate your OpenAPI document into your own tree and let the lead
agent diff it. `tools/ci/check-ownership.sh` enforces this and a crossing pull request is closed.

Never commit a provider API key. `MODEL_API_KEY` is read from the environment and `.env` is gitignored;
`tools/ci/check-secrets.sh` will catch a committed key, but by then it is exposed and must be rotated.

Commit subjects use the `be:` prefix, e.g. `be: enforce verified-over-unverified evidence precedence`.
