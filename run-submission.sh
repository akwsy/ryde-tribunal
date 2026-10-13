#!/usr/bin/env bash
set -euo pipefail
SUBMISSION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export READ_DATABASE_DSN="postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal_submission_v5_demo_test"
export TRIBUNAL_DATABASE_DSN="postgresql://ryde_submission_writer@localhost:5432/ryde_tribunal_submission_v5_demo_test"
export IMPORT_DATABASE_DSN="postgresql://ryde_submission_importer@localhost:5432/ryde_tribunal_submission_v5_demo_test"
export POLICY_VERSION="ryde-policy-1.0.0"
export POLICY_PATH="$SUBMISSION_ROOT/database/seed/policy/ryde-policy-1.0.0.json"
export MODEL_PROVIDER="${RYDE_SUBMISSION_PROVIDER:-openai_compatible}"
export MODEL_NAME="${RYDE_SUBMISSION_MODEL:-gemini-3.8-flash}"
export NEXT_PUBLIC_DEMO_FROM="2026-10-12"
export NEXT_PUBLIC_DEMO_TO="2026-10-13"
exec "$SUBMISSION_ROOT/run-local.sh"
