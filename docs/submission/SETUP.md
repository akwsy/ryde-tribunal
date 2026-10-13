# Isolated local submission setup

Use the integrated preview with Python 3.12, PostgreSQL 16 and Node 20+. Install backend/database
locked dependencies and frontend dependencies in their component directories. No Docker is required.

Generate synthetic data outside the checkout:

```
cd training
python -m ryde_training.generate --output /Users/allan/ryde-submission-data/corpus-v4
```

From the repository root, prepare the dedicated database. The name guard rejects ordinary company
or production database names. The command appends duplicate-safe synthetic imports, never reseeds:

```
PYTHONPATH=. python tools/submission/prepare_demo.py --bundle /Users/allan/ryde-submission-data/corpus-v4/synthetic-import.zip
```

Set backend/.env privately using the root template. Choose an actually available model, currently
Gemini 3.8 Flash or an available compatible provider, and set POLICY_VERSION=ryde-policy-1.0.0.
Configure all three DSNs against ryde_tribunal_submission_demo_test: readonly role
ryde_backend_readonly, writer role ryde_submission_writer and import role ryde_submission_importer.
Keep API keys in the private environment only. Run the existing run-local.sh after installing each
component's dependencies. Open localhost:3000. Test provider quota before recording.

This setup was exercised in /Users/allan/ryde-submission-preview. The original company database is
untouched. The current preview backend configuration is private and is not part of source archives.
The review queue and synthetic outputs are in /Users/allan/ryde-submission-data/corpus-v4.

If the model is unavailable, the source-backed fallback correctly routes to human review. That
behavior is an outage test, not proof of successful live adjudication. Never switch to recorded
fixtures and present them as a live-model run.
