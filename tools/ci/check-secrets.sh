#!/usr/bin/env bash
# Scans changed files for credentials, secrets, and personal data patterns.
# A hit fails the build and needs a human ruling.
#
# Portable to bash 3.2 (the macOS default) — no mapfile.
set -euo pipefail

BASE="${BASE:-origin/main}"

work="$(mktemp "${TMPDIR:-/tmp}/secretscan.XXXXXX")"
trap 'rm -f "$work"' EXIT

if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && \
   git rev-parse --verify "$BASE" >/dev/null 2>&1; then
  scope="changed vs $BASE"
  git diff --name-only "$(git merge-base "$BASE" HEAD)"...HEAD > "$work"
elif git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  scope="all tracked files"
  git ls-files > "$work"
else
  # No repository yet — scan the working tree so the guard is usable during setup.
  scope="working tree (no git repository)"
  find . -type f \
    -not -path './.git/*' -not -path './node_modules/*' -not -path './.next/*' \
    -not -path './.venv/*' -not -path './__pycache__/*' -not -path './dist/*' \
    -not -path './build/*' > "$work"
fi

# Assigned credential values: NAME = "value", not a bare NAME= with nothing after it.
cred_pattern='(api[_-]?key|secret|password|passwd|token|private[_-]?key|client[_-]?secret)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"'[:space:]]{8,}'
# Well-known credential shapes.
shape_pattern='(AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.)'
# Real-personal-data shapes. All data here is synthetic; a real email or SG mobile is a finding.
pii_pattern='([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\+65[ -]?[689][0-9]{7})'
# Addresses that are reserved for documentation and are therefore fine.
pii_allow='(example\.(com|org|net)|ryde\.test|\.invalid|localhost)'

status=0
scanned=0
report() { echo "  FAIL  $1"; status=1; }

while IFS= read -r f; do
  [ -n "$f" ] || continue
  [ -f "$f" ] || continue
  # The template is supposed to contain key NAMES without values.
  case "$f" in
    ./.env.example|.env.example) continue ;;
  esac
  scanned=$((scanned + 1))

  case "$f" in
    ./.env|.env|./.env.*|.env.*)
      report "$f — env files must never be committed" ;;
    *id_rsa*|*id_ed25519*|*.pem|*.p12|*.pfx|*.keystore)
      report "$f — key material" ;;
  esac

  if grep -q -EiI "$cred_pattern" "$f" 2>/dev/null; then
    report "$f — assigned credential value"
    grep -nEiI "$cred_pattern" "$f" | head -3 | cut -c1-100 | sed 's/^/          /'
  fi
  if grep -q -EI "$shape_pattern" "$f" 2>/dev/null; then
    report "$f — recognized credential format"
    grep -nEI "$shape_pattern" "$f" | head -3 | cut -c1-100 | sed 's/^/          /'
  fi
  if grep -EI "$pii_pattern" "$f" 2>/dev/null | grep -v -EI "$pii_allow" | grep -q .; then
    report "$f — possible real personal data (all data must be synthetic)"
    grep -nEI "$pii_pattern" "$f" | grep -v -EI "$pii_allow" | head -3 | cut -c1-100 | sed 's/^/          /'
  fi
done < "$work"

echo "secret scan: $scanned file(s), scope: $scope"

if [ "$status" -eq 0 ]; then
  echo "  ok    no findings"
else
  echo
  echo "Do NOT rewrite history to hide a committed secret — it is already exposed."
  echo "Stop, remove the secret from source, and rotate the credential before merging."
fi

exit "$status"
