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
  lead) allowed='.' ;;   # the lead agent owns shared/, docs/, tests/, tools/ and the root files
  *)
    echo "FAIL: branch '$BRANCH' has no recognized owner prefix (db/, be/, fe/, lead/)."
    exit 1
    ;;
esac

git rev-parse --verify "$BASE" >/dev/null 2>&1 || {
  echo "FAIL: base ref '$BASE' not found. Fetch first: git fetch origin main"
  exit 1
}

merge_base="$(git merge-base "$BASE" HEAD)"

work="$(mktemp -t ownership)"
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
  if printf '%s\n' "$f" | grep -q -E "$allowed"; then
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
