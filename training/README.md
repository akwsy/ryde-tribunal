# Synthetic data, human review, and training

All populated datasets, completed review files, calibration reports, and checkpoints stay outside
Git. No company exports or personal data may enter this workflow.

## Human review package

Generate a fresh reproducible corpus and 60-case review queue under current source-backed policy
1.1.0. The queue is split by scenario family into 40 train, ten validation, and ten test cases.
It contains separate draft rulings and targets for the Rider Advocate, Driver Advocate, and Judge.
Evidence auditor and fraud assessor stay on the validated baseline. The earlier policy 1.0.0
queue is retained as a historical artifact and must not be relabelled as policy 1.1.0.

The workbook has separate decision rows for each ruling and each of the three agent targets. The
offline live-output audit asks reviewers to score evidence use, citation accuracy, policy use,
fairness, and unsupported-claim handling from 1 (poor) to 5 (strong), with separate issue notes and
rationale fields. A reviewer must choose Pending, Approve, Correct, or Reject. Approval and correction require reviewer
identity, timezone-aware review time, policy version, and rationale. Ruling approval does not approve
the Judge target or either advocate target. Corrected targets must remain valid JSON with citations
that resolve to supplied records and policy rules.

Run the generator and review tools with Python 3.12 and `review-requirements.txt` installed. The
Excel workbook is built with `tools/training/build_review_workbook.mjs` using the provided
`@oai/artifact-tool` runtime. The completed workbook importer writes a new JSONL file; it never
overwrites the source queue:

```sh
PYTHONPATH=training python -m ryde_training.generate \
  --output /path/outside/repository/ryde-human-review-v1.1 \
  --policy-path database/seed/policy/ryde-policy-1.1.0.json

PYTHONPATH=training python -m ryde_training.audit \
  --report /path/to/diversified-benchmark-live-verified/report.json \
  --output /path/outside/repository/ryde-review-audit

node tools/training/build_review_workbook.mjs \
  --queue /path/to/ryde-human-review-v1.1/review-queue.jsonl \
  --audit /path/to/ryde-review-audit/live-output-audit.jsonl \
  --calibration /path/to/ryde-review-audit/confidence-calibration.json \
  --output /path/outside/repository/ryde-human-review.xlsx

PYTHONPATH=training python -m ryde_training.review_packet \
  --workbook /path/to/completed-review.xlsx \
  --source /path/to/ryde-human-review-v1.1/review-queue.jsonl \
  --output /path/outside/repository/reviewed-queue.jsonl
```

The saved 120-case live results support an offline quality audit of 30 cases (ten route, ten
no-show, ten adversarial/uncertainty) across the three core roles. Benchmark expected labels are
kept out of the workbook. Confidence metrics are diagnostic only because those results used policy
1.0.0; they are not current-policy claims or training data. The app's escalation threshold stays at
0.70 unless a separate evaluation supports a documented change.

## Export reviewed labels

Only individually approved role targets attached to an approved ruling can be exported. Rejected,
pending, corrected-but-unapproved, unresolved, stale-policy, or unprovenanced targets are excluded
or rejected. Train, validation, and test families remain isolated. An approved target must use a
human-reviewed origin and end with valid JSON; benchmark labels and deterministic outputs cannot
become training labels.

```sh
PYTHONPATH=training python -m ryde_training.review \
  --source /path/to/reviewed-queue.jsonl \
  --output /path/outside/repository/approved-v1.1
```

No labels are approved in the prepared packet. Do not train until the project owner has reviewed
each ruling and each role target. Training remains optional; verify free Kaggle GPU availability and
run the memory smoke before any full pilot. The configured LoRA pilot uses Qwen2.5-1.5B-Instruct,
seed 42, rank 16, alpha 32, dropout 0.05, learning rate 0.0002, two epochs, batch size one,
gradient accumulation 16, and a 4,096-token context. Reject overlength examples rather than dropping
decisive evidence.
