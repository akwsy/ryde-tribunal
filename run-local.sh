#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
BACKEND_PID=""
FRONTEND_PID=""

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$FRONTEND_PID" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
  if [[ -n "$BACKEND_PID" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "$FRONTEND_PID" ]]; then wait "$FRONTEND_PID" 2>/dev/null || true; fi
  if [[ -n "$BACKEND_PID" ]]; then wait "$BACKEND_PID" 2>/dev/null || true; fi
}

command -v curl >/dev/null 2>&1 || fail "curl is required."
command -v lsof >/dev/null 2>&1 || fail "lsof is required to check whether the app ports are already in use."
[[ -x "$BACKEND_DIR/.venv/bin/uvicorn" ]] || fail "Backend environment is missing. Set it up with: cd backend && uv sync"
[[ -x "$FRONTEND_DIR/node_modules/.bin/next" ]] || fail "Frontend packages are missing. Set them up with: cd frontend && npm install"
[[ -f "$BACKEND_DIR/.env" ]] || fail "Create backend/.env from the repository-root .env.example and configure the local database DSNs first."

for PORT in 8000 3000; do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    fail "Port $PORT is already in use. Stop the existing service and run this script again."
  fi
done

if ! grep -Eq '^READ_DATABASE_DSN=.+$' "$BACKEND_DIR/.env"; then
  fail "backend/.env needs a non-empty READ_DATABASE_DSN for the trip and archive database."
fi

if ! python3 - "$BACKEND_DIR/.env" <<'PY'
from pathlib import Path
from sys import argv, stderr
from urllib.parse import urlsplit

values = {}
for line in Path(argv[1]).read_text().splitlines():
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip("'\"")

required = ("READ_DATABASE_DSN", "TRIBUNAL_DATABASE_DSN")
missing = [key for key in required if not values.get(key)]
if missing:
    print(f"backend/.env is missing or empty: {', '.join(missing)}.", file=stderr)
    raise SystemExit(1)

for key in (*required, "IMPORT_DATABASE_DSN"):
    dsn = values.get(key, "")
    if dsn:
        db_name = urlsplit(dsn).path.strip("/").split("/", 1)[0].split("?", 1)[0]
        if db_name != "ryde_tribunal":
            print(f"backend/.env {key} targets database '{db_name}', not 'ryde_tribunal'.", file=stderr)
            raise SystemExit(1)

policy = values.get("POLICY_VERSION")
if policy != "ryde-policy-1.1.0":
    print(f"backend/.env POLICY_VERSION is '{policy}', expected 'ryde-policy-1.1.0' for new cases.", file=stderr)
    raise SystemExit(1)
PY
then
  fail "backend/.env validation failed. See the message above for the specific issue."
fi

trap cleanup EXIT INT TERM

printf 'Starting the Ryde Tribunal backend...\n'
(
  cd "$BACKEND_DIR"
  exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

printf 'Waiting for the backend and database...\n'
BACKEND_READY=0
for _ in {1..40}; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    fail "Backend stopped during startup. Check backend/.env and PostgreSQL."
  fi
  if curl -fsS http://127.0.0.1:8000/api/v1/health 2>/dev/null | grep -q '"database":"ok"'; then
    BACKEND_READY=1
    break
  fi
  sleep 0.5
done
[[ "$BACKEND_READY" -eq 1 ]] || fail "Backend did not connect to the database. Check that PostgreSQL is running and backend/.env has valid DSNs."

printf 'Starting the Ryde Tribunal frontend...\n'
(
  cd "$FRONTEND_DIR"
  export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000/api/v1"
  exec ./node_modules/.bin/next dev --hostname 127.0.0.1 --port 3000
) &
FRONTEND_PID=$!

printf '\nRyde Tribunal is starting at http://localhost:3000\n'
printf 'Press Ctrl+C to stop both services.\n\n'

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

fail "A service stopped unexpectedly. Check the startup output above."
