# QA / integration suite

This suite owns cross-component acceptance checks. It drives the public FastAPI HTTP surface and
uses independent in-memory QA records for offline runs; it does not call the orchestrator directly.

## Cold start

From the repository root, install the backend development environment with `cd backend && uv
sync --extra dev`, then run `cd .. && uv run --project backend pytest -q tests` (or activate the
backend environment and run `pytest -q tests`). The deterministic mock provider is the default.

For the seeded integration run, start PostgreSQL 16 with database `ryde_tribunal`, apply both
component migration sets, seed the current 100 users, 160 rides and 47 archive cases, and export
`RYDE_TEST_READ_DSN=postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal`. The QA
fixtures remain the deterministic acceptance baseline; a future live-stack job should additionally
start the backend with `READ_DATABASE_DSN` and exercise the same cases against HTTP.

The application currently uses policy `ryde-policy-1.1.0` for new cases. Earlier policy JSON files
are immutable snapshots used to explain historical decisions. The independent 120-case submission
benchmark remains pinned to `ryde-policy-1.0.0` as its historical baseline. The selective-routing
harness also defaults to `ryde-policy-1.0.0` for reproducibility; pass `--policy-version
ryde-policy-1.1.0` with the 1.1.0 policy file to run it against current policy. `docs/03-mock-policy.md`
describes the retired fictional test policy and is not an authority for live decisions.

## Offline judge-accuracy series

`backend/tests/test_judge_accuracy.py` exercises 31 independently authored synthetic cases across
all eight filing categories through the public filing and adjudication API. It checks six clear
rules-based rulings, nine evidence or policy hard stops, and sixteen human-reserved triage cases.
Expected labels are separate from records and filing prompts. A no-call provider guard ensures the
series cannot use Gemini or silently fall back to a generative model. It also validates policy and
evidence references for automatic rulings and verifies that human-reserved cases emit no verdict.

Run it offline with:

```
cd backend && .venv/bin/pytest -q tests/test_judge_accuracy.py
```

## Independent submission benchmark

`submission_benchmark.py` authors 120 independent scenarios directly from official source-backed
policy, without importing the runtime evaluator or training generator. Expectations stay outside
live records and archive search is empty, preventing label leakage through precedent.

Run with backend dependencies and PYTHONPATH pointing to the integrated backend:

```
python tests/submission_benchmark.py --policy /path/to/ryde-policy-1.0.0.json --output /path/outside/repo/baseline
```

Add `--live --env-file /path/to/private/backend/.env` to evaluate the configured live provider.
`--limit 2` is a smoke test only and must never be reported as a completed 120-case benchmark.
Use `--keys route-01 no-show-00` to probe one case per core category before running the full set.
Reports preserve all cases, fallback, citations, outcome accuracy and latency. Usage/cost are
unavailable and are recorded as null, never estimated as measured. Raw structured-output validity,
argument quality and calibrated confidence remain separate validation work.

## Selective Gemini routing benchmark

`selective_routing_benchmark.py` is a separate frozen 120-case routing test. It has 30 cases in
each of four paths: rules-clear no-call, verified-evidence no-call, model-eligible Gemini review,
and hard-stop human review. Its 25% expected Gemini share is intentionally stratified and is not
an estimate of production case prevalence. Expected labels remain in benchmark metadata only; the
API reader receives synthetic trip/evidence records, and precedent search is empty. The prior
`submission_benchmark.py` remains unchanged for historical comparison.

Run a local deterministic smoke first, then the live test with the configured Gemini provider.
Store populated output outside the repository:

```
backend/.venv/bin/python tests/selective_routing_benchmark.py --policy database/seed/policy/ryde-policy-1.1.0.json --policy-version ryde-policy-1.1.0 --output /path/outside/repo/selective-routing-smoke --keys clear-00 evidence-00 interpret-00 hardstop-03
backend/.venv/bin/python tests/selective_routing_benchmark.py --live --env-file backend/.env --policy database/seed/policy/ryde-policy-1.1.0.json --policy-version ryde-policy-1.1.0 --output /path/outside/repo/selective-routing-live --keys clear-00 evidence-00 interpret-00 hardstop-03
```

The report includes routing precision/recall, Gemini share, no-call and hard-stop safety rates,
outcome accuracy, citations, fallbacks, latency and provider-reported usage. A stratified routing
score is reported separately from the existing independent benchmark.

## Current-policy agent prompt smoke

`backend/tests/current_policy_agent_smoke.py` checks a small, independently labelled synthetic set
under Ryde policy 1.1.0: route-distance versus fare, reconciled and conflicting fare ledgers,
no-show timing, cancellation and waiting vouchers, and a driver-payout boundary. It always uses an
in-memory reader and blanks both database DSNs. Run the offline pass first, with reports outside Git:

```
cd backend
.venv/bin/python tests/current_policy_agent_smoke.py --output /path/outside/repo/current-policy-smoke-offline
.venv/bin/python tests/current_policy_agent_smoke.py --live --env-file .env --model gemini-3.1-flash-lite --output /path/outside/repo/current-policy-smoke-live
```

The report records configured provider identity, actual provider calls by role, validation findings,
fallback, latency, and usage when returned. A live-configured run with zero provider calls verifies
only routing; it does not verify that Gemini received or followed an updated prompt. Do not weaken
the human-review gates just to create a provider call.

Contract checker: run `node tests/contract_check.mjs --case-id DSP-000045` against the app, or
pass `--payload-file` and `--policy-file` to validate a saved synthetic response offline. It
uses the YAML and JSON Schema packages already installed with the frontend and checks CaseResult,
trace and policy against `shared/openapi.yaml`; no extra Python QA packages are needed.
