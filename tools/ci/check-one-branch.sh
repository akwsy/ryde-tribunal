#!/usr/bin/env bash
# Enforces docs/06-git-workflow.md §2: each specialist holds AT MOST ONE branch at a time.
# Counts branches on the remote per owner prefix. Exit 1 if any owner holds more than one.
# Run before cutting a branch, and in CI on every pull request.
#
# Portable to bash 3.2 (the macOS default) — no mapfile, no associative arrays.
set -euo pipefail

REMOTE="${REMOTE:-origin}"
PREFIXES="db be fe lead"
status=0

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "FAIL: not inside a git repository."
  exit 1
}

git remote get-url "$REMOTE" >/dev/null 2>&1 || {
  echo "FAIL: remote '$REMOTE' is not configured. The repository is not set up yet (see docs/06-git-workflow.md §8)."
  exit 1
}

git fetch --prune "$REMOTE" >/dev/null 2>&1 || {
  echo "FAIL: cannot reach remote '$REMOTE'."
  exit 1
}

work="$(mktemp "${TMPDIR:-/tmp}/one-branch.XXXXXX")"
trap 'rm -f "$work"' EXIT

# Every remote branch that is not main or HEAD.
git for-each-ref --format='%(refname:strip=3)' "refs/remotes/$REMOTE" \
  | grep -v -E '^(HEAD|main)$' > "$work" || true

echo "one-branch check (remote: $REMOTE)"

for prefix in $PREFIXES; do
  count=$(grep -c -E "^${prefix}/" "$work" || true)
  count=${count:-0}
  if [ "$count" -gt 1 ]; then
    echo "  FAIL  ${prefix}/  holds $count branches:"
    grep -E "^${prefix}/" "$work" | sed 's/^/          - /'
    status=1
  elif [ "$count" -eq 1 ]; then
    echo "  ok    ${prefix}/  $(grep -E "^${prefix}/" "$work")"
  else
    echo "  ok    ${prefix}/  (slot free)"
  fi
done

# A branch with no recognized owner prefix is also a violation: ownership must be legible.
while IFS= read -r branch; do
  [ -n "$branch" ] || continue
  owner="${branch%%/*}"
  recognized=0
  for prefix in $PREFIXES; do
    [ "$owner" = "$prefix" ] && recognized=1
  done
  if [ "$recognized" -eq 0 ]; then
    echo "  FAIL  unowned branch '$branch' — every branch must start with db/, be/, fe/, or lead/"
    status=1
  fi
done < "$work"

if [ "$status" -ne 0 ]; then
  echo
  echo "The one-branch rule is violated. Merge or delete the extra branch before continuing:"
  echo "  git push $REMOTE --delete <branch>"
fi

exit "$status"
