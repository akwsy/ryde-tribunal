# Ryde Tribunal

**Track:** Ryde / Digital Native — Multi-Agent Autonomous Dispute Resolution System

**Short blurb:** Fair ride disputes, resolved through evidence and policy.

## Who it serves

Ryde support reviewers investigate rider and driver disputes involving uncertain timelines,
route choices and fare charges. Evidence is scattered across GPS, communications, events and
payment records. Ryde Tribunal brings both parties' cases into one auditable workspace.

## Product and workflow

A reviewer files a simulated dispute against a recorded trip. Rider and Driver Advocate agents
select evidence through bounded read-only tools and present opposing, evidence-grounded positions.
An impartial Judge receives both structured cases, current policy, audit findings and advisory
precedents. It proposes a decision, supported facts, explanation and confidence. Post-model checks
withhold unsupported remedies and incomplete or contradictory cases for human review.

The UI displays the decision, evidence records, official policy links and actual agent activity.
Reviewers approve or override a proposal with a separate recorded decision. Outcome summaries can
be exported for both parties. Financial remedies are recommendations; this prototype executes no
payments or vouchers.

## Business and technical architecture

Next.js/React reviewer UI → FastAPI application → source-isolated PostgreSQL records and evidence.
Three core model roles use a configurable compatible provider. Evidence audit and fraud assessment
are advisory support roles. Archived human decisions and model proposals remain distinct. Current
published policy takes priority over precedent, and old fictional policies remain historical only.

Prompts supply the dispute, allowed evidence tools, verified facts, stable policy IDs and explicit
JSON schemas. Nested evidence is data rather than an instruction channel. Citation validators check
case ownership, visibility, exact field and observed value. Missing information remains unknown.

## Source-backed decisions

Published Ryde sources specify three-minute cancellation/wait windows, scheduled-trip grace,
service exclusions and waiver processes. Eligible cancellation and waiting waivers are voucher
recommendations, with the published filing window. Route distance does not supply an invented
refund formula. Unclear policy application requires review. Engineering escalation controls are
labelled Tribunal operating rules rather than attributed to Ryde.

## Value and measurement

Measure end-to-end latency, standard-case automatic resolution, outcome accuracy, invalid citations,
escalation correctness and fallback frequency. The independent 120-case synthetic benchmark is
isolated from the training corpus and precedent retrieval. Do not claim production savings or
accuracy from synthetic evaluation alone.

For a business scenario, with N monthly tickets, reviewer minutes M and fully loaded hourly cost C,
the baseline handling cost is N × M/60 × C. Estimate potential savings by multiplying that amount
by the measured fraction of cases that safely avoid review; report assumptions separately from
measured prototype results. No Ryde operational figures are asserted by this prototype.

## Responsible AI and current limits

Every source record retains provenance. Model proposals do not become training labels without
human approval. Role transcripts require individual review. The 1,000-case corpus is entirely
synthetic and populated outputs remain outside Git. No company data was used in live evaluation.

The local app has no authentication and is intended for one authorised reviewer. Public deployment,
image analysis and production payout integration are deferred. Provider availability and quota
failures currently prevent a complete live-model readiness sign-off. The deterministic fallback is
visibly labelled and requires review under the source-backed policy. Fine-tuning and GPU access are
not claimed as completed. Genuine CodeBuddy/WorkBuddy evidence must be supplied before submission.
