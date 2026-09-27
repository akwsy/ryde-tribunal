# 03 — Mock Ryde policy `ryde-policy-0.1.2`

Fictional policy for a synthetic system. Written as **prose with stable rule ids**, deliberately: the
Judge reasons from this text, and the eval corpus is authored from this text by someone other than the
implementer of the policy module (integrity rule I-4). The machine-readable copy lives at
`database/seed/policy/ryde-policy-0.1.2.json` and is the single source of truth for current cases (D-18).
The immutable `ryde-policy-0.1.0.json` and `ryde-policy-0.1.1.json` files remain available for historical records.

Rules state **conditions and remedies available**, never a precomputed verdict for a case.

## Fare and refund principles

**RP-FARE-001.** A rider is charged the fare quoted at booking unless the trip materially deviates from
the quoted trip. Where a deviation is attributable to the driver, the rider is entitled to a refund of
the *excess* over the quoted fare, not the whole fare.

**RP-FARE-002.** Surge pricing applied at booking is valid for the whole trip and is not itself grounds
for a refund. A surge multiplier applied after booking is invalid.

**RP-FARE-003.** A promotion applied at booking must be honoured. A promotion that failed to apply
entitles the rider to the promotional difference.

**RP-FARE-004.** Goodwill compensation up to SGD 15.00 may be offered where a rider experienced a real
service failure that policy does not otherwise remedy.

## Route deviation

**RP-ROUTE-001.** The planned route is the route offered at booking. Actual distance is measured from
device telemetry.

**RP-ROUTE-002.** A deviation up to **15%** of planned distance is within normal operating tolerance
(traffic, closures, one-way systems) and is not overcharging.

**RP-ROUTE-003.** A deviation above **15%** requires justification. Recognised justifications are: a
rider-requested change, a road closure or diversion evidenced by conditions data, a safety
consideration, or a pickup/dropoff point adjustment. Unjustified deviation above 15% entitles the rider
to a refund of the excess fare attributable to the extra distance.

**RP-ROUTE-004.** A stop not requested by the rider and longer than **4 minutes** is an unexplained
stop. Its waiting charge is refundable, and it counts toward materiality.

**RP-ROUTE-005.** Trip duration above **130%** of the estimate, where distance is within tolerance, is
attributable to traffic and is not refundable on its own.

## No-show and cancellation

**RP-NOSHOW-001.** A cancellation fee is valid only where the driver arrived at the pickup point,
waited the required **5 minutes** after arrival, and attempted contact at least once.

**RP-NOSHOW-002.** Arrival means telemetry places the driver within **100 m** of the pickup point.
Where telemetry never places the driver within 100 m, the fee is invalid and fully refundable.

**RP-NOSHOW-003.** Contact attempt means a call or a chat message to the rider recorded in the platform.
An unanswered attempt still counts as an attempt.

**RP-NOSHOW-004.** Where the driver waited less than 5 minutes or made no recorded contact attempt, the
fee is invalid.

**RP-NOSHOW-005.** Where the rider cancelled before the driver was assigned, no fee applies.

## Property damage and cleaning

**RP-DAMAGE-001.** A cleaning fee requires evidence that the mess occurred during the trip and was
caused by the rider. Fees are tiered: minor SGD 20.00, moderate SGD 50.00, major SGD 120.00.

**RP-DAMAGE-002.** Photographic evidence must be timestamped within **2 hours** of trip end. Evidence
whose authenticity cannot be established is treated as unverified, not as absent.

## Safety

**RP-SAFETY-001.** A safety incident normally requires human review. An automated ruling is eligible
only when the Judge lists every decisive fact, every cited evidence ID resolves to verified evidence,
the evidence audit reports no material contradiction, factual error, or fabrication finding, and Judge
confidence meets the configured escalation threshold. Missing or unknown evidence or materiality
requires human review with a summary.

**RP-SAFETY-002.** Threatening or abusive language in the chat log is a safety signal independent of the
fare question and must be surfaced to the reviewer; a safety signal always requires human review even
when the fare dispute itself is clear.

## Evidence and decision-making

**RP-EV-001.** System records (telemetry, fare ledger, platform timestamps, in-app messages) are
verified evidence. Party statements outside the platform are unverified.

**RP-EV-002.** Where verified and unverified evidence conflict on the same factual question, verified
evidence prevails. Unverified evidence may raise uncertainty and trigger escalation; it may not by
itself reverse a finding grounded in a verified record.

**RP-EV-003.** Where the evidence needed to decide is missing, contradictory, or internally
inconsistent, the case is insufficient and is escalated. An adverse inference is not drawn against
either party for absent system data.

**RP-EV-004.** Prior dispute history informs fraud assessment and may not by itself decide a case. A
rider with many prior disputes is still entitled to a remedy where this case's evidence supports one.

**RP-PREC-001.** Prior rulings are advisory. Similar cases should be decided consistently, but a
precedent does not bind where this case's evidence or the current policy version differs. A precedent
decided under an earlier policy version must be cited with that version.

## Escalation

**RP-ESC-001.** Escalate when Judge confidence is below the approved threshold (D-09: `0.70`).

**RP-ESC-002.** Escalate when the case is materially uncertain, contradictory, insufficient, or
inaccurate.

**RP-ESC-003.** Escalate when the case is high impact (D-10: money ≥ SGD 25.00, a safety category
that does not meet RP-SAFETY-001 auto-ruling eligibility, or ≥3 disputes by the same party in 30 days). Fraud risk informs the Judge's ruling and does not by
itself trigger escalation.

**RP-ESC-004.** Escalate when the remedy the evidence supports exceeds the automated ruling caps
(D-11).

**RP-ESC-005.** An escalated case carries a complete human-review summary: the question to decide, the
evidence relied on, the conflict or gap that caused escalation, and what each advocate argued.
