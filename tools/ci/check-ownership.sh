#!/usr/bin/env bash
# Enforces docs/00-ownership.md §1: a branch may change only its owner's paths.
# The branch prefix declares the owner; the diff against main must stay inside that owner's tree.
# Run before pushing, and in CI on every pull request.
#
# Portable to bash 3.2 (the macOS default) — no mapfile.
set -euo pipefail

BASE="${BASE:-origin/main}"
BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
owner="${BRANCH%%/*}"

case "$owner" in
  db)   allowed='^database/' ;;
  be)   allowed='^backend/' ;;
  fe)   allowed='^frontend/' ;;
  qa)   allowed='^tests/' ;;
  ml)   allowed='^training/' ;;
  # The lead agent owns shared/, docs/, tools/, .github/ and the root files — but NOT a specialist's
  # tree. This exclusion is deliberate: PR #5 swept a specialist's entire working tree onto main
  # through a lead/ branch because 'lead' was allowed everything, bypassing the review gate.
  # tests/ moved to qa and training/ to ml, so both are forbidden here too.
  lead) allowed='.'; forbidden='^(database|backend|frontend|tests|training)/' ;;
  *)
    echo "FAIL: branch '$BRANCH' has no recognized owner prefix (db/, be/, fe/, qa/, ml/, lead/)."
    exit 1
    ;;
esac
forbidden="${forbidden:-}"

git rev-parse --verify "$BASE" >/dev/null 2>&1 || {
  echo "FAIL: base ref '$BASE' not found. Fetch first: git fetch origin main"
  exit 1
}

merge_base="$(git merge-base "$BASE" HEAD)"

work="$(mktemp "${TMPDIR:-/tmp}/ownership.XXXXXX")"
trap 'rm -f "$work"' EXIT
git diff --name-only "$merge_base"...HEAD > "$work"

if [ ! -s "$work" ]; then
  echo "ownership check: no changes against $BASE"
  exit 0
fi

echo "ownership check: branch '$BRANCH' (owner: $owner) vs $BASE"

status=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if [ -n "$forbidden" ] && printf '%s\n' "$f" | grep -q -E "$forbidden"; then
    echo "  FAIL  $f  — '$owner' may not commit another owner's tree"
    status=1
  elif printf '%s\n' "$f" | grep -q -E "$allowed"; then
    echo "  ok    $f"
  else
    echo "  FAIL  $f  — outside the '$owner' tree"
    status=1
  fi
done < "$work"

if [ "$status" -ne 0 ]; then
  echo
  echo "This branch crosses an ownership boundary (docs/00-ownership.md §1)."
  echo "A pull request that touches another owner's paths is CLOSED, not fixed in review."
  echo "Need a change there? File an integration request with the lead agent."
fi

exit "$status"
