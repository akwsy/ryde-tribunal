# Evaluation and API checks

The main offline Judge accuracy suite is in `backend/tests/test_judge_accuracy.py`. It covers all eight dispute categories with expected outcomes kept separate from the records sent to the app.

Run the API contract check against a running local app:

```bash
node tests/contract_check.mjs --case-id DSP-000045
```

The source-authored evaluation suites in this directory measure adjudication accuracy and selective model routing. They use synthetic records and should be run with the offline provider first. Store populated reports outside the repository.
