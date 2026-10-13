# Submission readiness — 13 October 2026

**Status: implementation preview available; NOT ready to submit.**

## Implemented and checked

- Source-backed policy 1.0.0 with official URLs and explicit Tribunal operating rules.
- Voucher delivery, bounded evidence selection, persisted agent traces and party summaries.
- Light reviewer workspace, fixture-mode notice, policy disclosures, useful empty states and text chart data.
- Separate synthetic-only submission PostgreSQL database and least-privilege demo connections.
- 1,000 generated synthetic cases and a separate 60-case human review queue outside Git.
- Independent 120-case API benchmark and guarded LoRA training pipeline.
- Backend: 126 passed including five PostgreSQL integration tests; database: 55 passed.
- Frontend: 195 passed, TypeScript and production build passed. Cross-component QA: ten passed.
- Synthetic ZIP validated and imported (24 users, 12 trips). Existing company data was not reseeded.

## Remaining gates

- Genuine complete live-model adjudication for both core categories. Current calls encounter
  provider HTTP 503 availability and HTTP 429 quota limits; all complete smoke cases fell back.
- Full live benchmark accuracy >=90% and clear-standard automatic resolution >=80%.
  The offline scripted benchmark is deliberately conservative and does not establish these targets.
- Raw structured-output metrics, independent argument-quality review and confidence calibration.
- Final recording and genuine live-model walkthrough after provider recovery.
  Assembly, restart persistence, synthetic import and contract checks have passed in offline mode.
- Human review of training rulings and all three role targets; zero training labels approved.
- Kaggle GPU verification, optional smoke/train/evaluate run. Fine-tuning does not block submission.
- Genuine CodeBuddy/WorkBuddy evidence: at least three screenshots or a recording.
- Final six-minute live walkthrough video after live-model gates pass.
- Confirm exact 16 October cutoff, registration, Singapore eligibility, team size and judge access.
- Owner/reviewer merge of component PRs, final revision and submission receipt.

## Submission items

Title and blurb: PROJECT-DESCRIPTION.md. Architecture: architecture.svg. Cover: cover-1920x1080.png
and cover-380x216.png. Recording: DEMO-SCRIPT.md; final video pending. Tool evidence:
WORKBUDDY-TASKS.md; genuine screenshots pending. Source: component pull requests and integration
preview. Never turn a pending item into a checkmark without its evidence.
