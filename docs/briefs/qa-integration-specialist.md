# Brief — QA / integration specialist

Phase Zero, final gate. You are the fourth specialist and you own `tests/`, the cross-component
acceptance suite. Read `docs/00-ownership.md`, `docs/02-api-contract.md`, `docs/04-integrity-rules.md`,
`docs/06-git-workflow.md`, and this project's `docs/05-integration-log.md` — that log is the most
important document for your role, because it records every defect this project has actually shipped and
every one of them was your job's shape.

## 1. Mission and scope

Write the cross-component acceptance tests for the handoff's §8.4 criteria: a case travelling
database → API → advocates → Judge → frontend, with the result traceable back to the records that
produced it.

**Why this role exists, stated plainly.** All three components pass their own suites — backend 66,
database 16, frontend 145 — and every real defect this project has had still slipped through. The
policy loader could not read the canonical file. The tribunal issued a confident monetary ruling with
zero evidence and no escalation. The evidence endpoint 422'd on ids its own rulings referenced. Two
separate code paths invented remedies that no charge supported. Each component was internally correct
and internally tested; the bugs lived between them. Your suite is the only layer that can see that
space. Write tests that would have caught those five, then find the sixth.

## 2. Non-goals

- You do not fix defects. You find them, prove them with a failing test, and report to the lead agent,
  who routes the fix to the owning specialist. A test you wrote plus a defect you fixed yourself is two
  specialists' work in one branch.
- You do not modify `backend/`, `database/`, `frontend/`, `shared/` or `docs/`. If a contract is wrong,
  say so; do not edit it.
- You do not duplicate a component's own unit tests. If a test passes or fails entirely within one
  component, it belongs to that component.

## 3. Allowed paths

`tests/**` — `tests/`, `tests/fixtures/`, `tests/README.md`, `tests/ASSUMPTIONS.md`, and a
`tests/pyproject.toml` for your own dependencies.

## 4. Forbidden paths

`backend/**`, `database/**`, `frontend/**`, `shared/**`, `docs/**`, `tools/**`, `.github/**`, and the
root files.

## 5. Contracts

**Input.** `shared/openapi.yaml` is the authoritative HTTP contract — assert against it, not against what
the backend happens to return. `docs/02-api-contract.md` §5–6 for the read contract and the write matrix.
`docs/03-mock-policy.md` for policy semantics. The components' own handoff artifacts
(`backend/handoff/`) are readable for conformance.

**Output.** A runnable suite plus `tests/README.md` documenting exactly how to bring up each dependency
and run it, and `tests/ASSUMPTIONS.md` for anything you had to assume.

## 6. Dependencies and assumptions

*Given:* PostgreSQL 16 on `:5432`, database `ryde_tribunal`, already migrated and seeded (60 rides,
32 archive cases). Python 3.12 via `uv`. Node 20 for the frontend. The backend reads through
`READ_DATABASE_DSN` as role `ryde_backend_readonly`; the frontend reads
`NEXT_PUBLIC_API_BASE_URL`. `MODEL_PROVIDER=deterministic_mock` is the offline default.

*Useful seeded facts:* `RIDE-000001` has a 48.3% route deviation and was charged **below** the quoted
fare. `RIDE-000002` has `cancellation_fee_cents = 0`. `RIDE-000010`, `RIDE-000030`, `RIDE-000050` each
have a 500-cent cancellation fee. Archive ids are `DSP-ARCH-*`.

*Ambiguous → ask.* If a criterion cannot be tested without inventing behaviour, report that rather than
weakening the test to make it pass.

## 7. Required tests — the handoff's §8.4, plus the regression set

Cross-component flow:

- A seeded **route-deviation** case travels database → API → advocates → Judge → frontend.
- A seeded **no-show** case travels the same flow.
- The returned ruling is **traceable**: every `judge.evidence_references` id and every advocate citation
  resolves through `GET /evidence/{id}` with a matching `case_id`, each citation's `observed_value`
  equals the `ride_data` row it names, and the recorded `policy_version` matches the loaded document.
- **Database unavailable** produces a clear backend error and **no** ruling — assert no `judge` key.
- A **malformed or incomplete** evidence record surfaces as uncertainty or escalation, never as fact.
- A **human override** is stored and becomes visible in case history without destroying the original
  ruling.
- Each component's own tests can still run independently from documented fixtures.

Regression tests for defects this project actually shipped — write these first, because they are known
to be catchable:

- The policy document the backend loads is the **canonical seed file**, and every rule id in
  `docs/03-mock-policy.md` is present in it with **matching text**. This one currently FAILS: 22 of 28
  rules diverge. Write it, watch it fail, report it — do not skip it.
- No ruling is ever returned with an **empty** evidence bundle: advocate claims > 0 and citations > 0 on
  every adjudicated case, across every category.
- A `refund` or `compensation` ruling **always** carries a positive `amount`.
- A case whose remedy computes to zero is **not** a refund, and a filing contradicted by the verified
  record **escalates**.
- `synthetic_reasoning` is true whenever the mock provider ran, and the frontend renders its badge.
- An archive accessor **raises** on a live `DSP-*` id (integrity rule I-2a).
- A live `case_facts` payload contains **no** outcome-shaped key.

## 8. Passing criteria

The suite runs from a documented cold start; every test either passes or is a reported defect with a
named owning component; no test is skipped to make the run green; and `tests/README.md` lets someone
else reproduce it. A suite that passes while the known policy-text divergence exists has been written
wrong.

## 9. Handoff artifacts

`tests/README.md`, `tests/ASSUMPTIONS.md`, the run log, and a defect report table — one row per failure
with the criterion, the observed behaviour, and the component you believe owns it.

## 10. Git and GitHub

Read `docs/06-git-workflow.md` in full. It is binding.

- **Your branch prefix is `qa/`.** Branch from `main`, never from another specialist's branch.
- **You hold at most one branch at a time** — one in existence, not one in progress. Merged and deleted
  before the next.
- Work in your **own clone**, never in another agent's working tree.
- **Push to GitHub when your changes are done**, then open a pull request against `main`. Before pushing:
  `BASE=origin/main bash tools/ci/check-ownership.sh`, `bash tools/ci/check-secrets.sh`,
  `bash tools/ci/check-one-branch.sh`.
- Your diff stays inside `tests/`. Do not commit `.venv/`, `node_modules/` or captured output.
- Do not push to `main`. Do not merge your own pull request — the lead agent merges.

A failing test in your PR is expected and welcome when it documents a real defect. Say so in the PR body
and name the owning component; do not delete it or mark it `xfail` to get a green run.

Commit subjects use the `qa:` prefix, e.g. `qa: assert the loaded policy matches the canonical seed`.
