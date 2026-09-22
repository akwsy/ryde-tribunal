# 04 — Integrity rules (non-negotiable)

The handoff's central requirement is that the three model components reason **from the case**, not from
hardcoded outcomes or response templates. That requirement is easy to satisfy on paper and easy to
violate in code, in ways that pass a naive test suite. These rules exist to make the violation
impossible rather than merely discouraged. Every rule has a named owner and an enforcing test.

## I-1 — The policy engine must not pre-compute the verdict

The failure mode: a rules engine computes `recommendation = REFUND` from thresholds, the Judge is
handed that recommendation, and in mock mode the Judge copies it. The system then *looks* agentic while
being a scripted rules engine with a language-model veneer.

Rule: the policy layer may return only

- the set of applicable policy rule ids and their text, and
- **factual measurements** (e.g. `actual_distance_km`, `planned_distance_km`, `deviation_pct = 34.2`,
  `wait_time_s`, `surge_multiplier`),

and may **never** return a ruling type, a recommended action, a monetary amount, or a
fault attribution. The mapping from measurement + policy text to a ruling is the Judge's, and the
Judge's alone.

*Owner:* backend. *Test:* `tests/test_i1_no_precomputed_verdict.py` asserts the policy layer's return
type has no field matching `/rul(e|ing)_type|verdict|recommend|action|amount|fault|refund/i`, and
that `PolicyContext` is a frozen dataclass whose fields are measurements and rule references only.

## I-2 — Live evidence carries no outcomes; the archive is disjoint and advisory

Two separate stores, two separate schemas.

- **Live ride/evidence store** (`ride_*`, `case_*` for the case under adjudication): contains **no**
  outcome, verdict, fault, expected-result, or ground-truth field. A case being adjudicated cannot
  look up its own answer.
- **Historical dispute archive** (`archive_*`): contains verdicts, recommended actions, confidence,
  decision origin (human/agent), and human-override records. It is keyed to a **disjoint identifier
  namespace** — `RIDE-ARCH-*`, `DSP-ARCH-*` — that must never collide with runtime `RIDE-*` / `DSP-*`
  ids, and there is no foreign key from an archive row to a live ride.

Precedent from the archive is **advisory and non-binding**: the Judge may cite it as support, may not
treat it as controlling, and must state the ruling's basis in policy independently of it.

*Owner:* database. *Tests:* a schema guard scanning live-table column names against
`/expected|verdict|outcome|resolution|fault|ground.?truth|correct|is_valid|refund_granted/i`; an
id-disjointness test asserting `archive_* ∩ live_* = ∅` on every identifier column.

**I-2a — an archive read must refuse a live identifier.** The near-miss that produced this rule: the
contract's original `get_case(case_id)` was read by the backend as the live dispute and implemented by the
database specialist as an archived case. Had both shipped, the backend would have fetched an
outcome-bearing archive record for the case it was adjudicating — I-2 defeated not by a bad column but by
an ambiguous function name.

Rule: every archive accessor takes an explicitly archive-namespaced argument, validates it against
`^DSP-ARCH-\d+$` or `^RIDE-ARCH-\d+$`, and **raises** on a live `DSP-*` / `RIDE-*` id rather than
returning anything. There is no accessor for the live case at all — it lives in the backend's `tribunal`
schema (see `docs/02-api-contract.md` §6).

*Owner:* database implements the guard; backend must not route a live id to an archive call. *Test:*
`get_archive_case("DSP-000045")` raises; `get_archive_case("DSP-ARCH-000017")` succeeds.

## I-3 — Citation validation is semantic, not referential

Checking that a cited evidence id exists proves nothing: a model can cite a real record that does not
support its claim. Every citation must carry the **specific field** it relies on and the **value** it
read, and validation must check:

1. the evidence id exists,
2. it belongs to **this** case (`case_id` match),
3. the cited `field_path` exists on that record,
4. the `observed_value` in the citation equals the stored value (within a declared tolerance for
   floats),
5. the citing actor was entitled to see it (role/visibility match),
6. `rejectedEvidence` ids are validated on the same terms as accepted ones.

A citation that fails any check is recorded as `invalid_citation` and lowers the argument's weight. The
metric is reported as `invalid_citation_rate` — never as "unsupported claim rate", which it is not.

*Owner:* backend. *Test:* `tests/test_i3_citation_semantics.py` includes a case where an advocate cites a
real, same-case record whose value contradicts the claim; validation must reject it.

## I-4 — Evaluation must not be a self-consistency test

Forbidden: expected outcomes derived from the same threshold constants the system uses to decide, or an
eval harness that calls internal functions and bypasses the API.

Required:

- expected outcomes in `tests/fixtures/eval_corpus.json` are authored **from the policy prose** in
  `docs/03-mock-policy.md` by a party that is not the implementer of the policy module, and each case
  records `expected_policy_ids` that the harness **actually asserts** against the ruling,
- the harness drives the **public HTTP API**, not `orchestrator.run_case(...)`,
- boundary coverage: for every numeric policy threshold, one case just inside and one just outside.

*Owner:* lead agent authors the corpus; backend runs it. *Test:* the harness fails if
`expected_policy_ids` is present and unasserted, and CI rejects an eval module importing from
`backend/app/policy/`.

## I-5 — Two different cases must not yield the same argument

*Owner:* backend. *Test:* `tests/test_i5_case_specificity.py` runs ≥6 materially different cases per
category and asserts, on normalized advocate argument text (lowercased, ids and numbers stripped),
pairwise similarity below a declared ceiling, and that each argument cites a distinct evidence id set.
Identical output across two cases in a category is a hard failure, not a warning.

## I-6 — Scripted providers must be labelled as scripted, everywhere

A deterministic fallback provider is legitimate — it keeps the system testable and keeps a
ruling possible when the external API is down. Presenting its output as agent reasoning is not.

Every ruling payload carries, per model component:

```json
"provider": { "kind": "llm" | "deterministic-mock", "model": "…", "policy_version": "ryde-policy-0.1.0" }
```

When any component ran as `deterministic-mock`, the ruling carries
`"synthetic_reasoning": true`, and the frontend must show a visible badge on the case page. The UI must
not label scripted output "Advocate reasoning" or "Judge deliberation" without that badge.

*Owner:* backend emits, frontend renders. *Test:* frontend component test asserts the badge appears
whenever `synthetic_reasoning` is true; backend test asserts the field is never absent.

## I-7 — Unverified evidence cannot outrank a verified record

An appeal or a late submission is re-adjudicated with the new evidence appended, which means an
unverified claim can otherwise flip a decision that verified telemetry had settled.

Rule: every evidence item carries `verification: {status: verified|unverified|disputed|unverifiable,
method, uncertainty_pct}`. Precedence is explicit and enforced in code: a `verified` system record
(GPS, fare ledger, timestamps) outranks `unverified` party-submitted text on the same factual question.
An `unverified` item may raise uncertainty, trigger escalation, or support a claim that no verified
record speaks to — it may not by itself reverse a finding grounded in a verified record.

*Owner:* backend. *Test:* an appeal case where unverified chat text contradicts verified GPS must not
flip the ruling; it must either hold or escalate.

## I-8 — External information is quarantined

External LLM/API content is stored and passed in a separate `external_findings` collection, never merged
into case evidence. Each finding carries `source_url`, `retrieved_at`, `reliability`, and an
`evaluation` verdict recorded before it may be cited. It cannot override case evidence or policy. If
the external call fails, the ruling proceeds on native evidence when safe, records
`external_unavailable: true`, and fabricates nothing.

*Owner:* backend. *Test:* with the external provider forced to fail, the API still returns a ruling
whose `external_findings` is empty and `external_unavailable` is true.
