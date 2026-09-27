# 06 — Git and GitHub workflow

Authoritative for every specialist. Two owner-set rules drive this document:

1. **A specialist pushes to GitHub whenever it is done with its changes.** Work does not sit unpushed on
   a local machine.
2. **A specialist may hold at most one branch at a time.** One live branch per specialist, globally —
   local and remote.

Everything below exists to make those two rules checkable rather than merely stated.

## 1. Branch model

**Each specialist works in its OWN clone**, not in a directory anyone else is using. The lead agent's
checkout is off limits. This is not tidiness: a specialist working inside the lead agent's tree once
caused `git add -A` on a `lead/` branch to sweep that specialist's entire component onto `main`
unreviewed, bypassing its own open pull request (PR #5, unwound by PR #6). Clone to a path you own:

```bash
git clone https://github.com/akwsy/ryde-tribunal.git ryde-tribunal-<your-prefix>
```

`main` is the only long-lived branch. It is protected by convention and by CI (see §8 for why
server-side protection is unavailable): no direct pushes, no force-pushes, no deletion. Every change
reaches it through a pull request opened from a specialist branch.

Each specialist owns exactly one branch prefix, and the prefix is how ownership is enforced
mechanically:

| specialist | prefix | example |
|---|---|---|
| Database | `db/` | `db/phase0-schema-and-seed` |
| Backend / model | `be/` | `be/phase0-tribunal-orchestration` |
| Frontend | `fe/` | `fe/phase0-case-view` |
| QA / integration | `qa/` | `qa/phase0-cross-component` |
| Model training | `ml/` | `ml/phase1-kaggle-training` |
| Lead agent | `lead/` | `lead/phase0-contracts` |

Branch names are lowercase, hyphenated, and carry the phase: `<prefix><phase>-<topic>`.

## 2. The one-branch rule

At any moment a specialist has **at most one** branch in existence — not one *in progress*, one *in
existence*. Concretely:

- Before cutting a new branch, the specialist's previous branch must be **merged and deleted** on both
  the remote and locally.
- A specialist may not open a second branch to "park" work, to try an alternative approach, or to split a
  large change. If the work is too large for one branch, it is too large for one section — say so and the
  lead agent will split the section instead.
- A specialist may not branch off another specialist's branch, ever. Branch from `main` only.
- Abandoned work is deleted, not left behind. A branch whose PR is closed unmerged is deleted
  immediately, which frees the specialist's single slot.

Enforced by `tools/ci/check-one-branch.sh`, which fails when any prefix has more than one branch on the
remote. It runs in CI on every pull request and is the lead agent's pre-merge check.

## 3. The cycle a specialist runs

```bash
# 1. Start clean, from main, with no branch of your own alive.
git checkout main && git pull --ff-only origin main
bash tools/ci/check-one-branch.sh        # must pass before you cut anything

# 2. Cut your one branch.
git checkout -b db/phase0-schema-and-seed

# 3. Work. Commit in small, reviewable steps inside YOUR paths only.
git add database/
git commit -m "db: add ride telemetry tables and outcome-freedom guard"

# 4. Verify before pushing — a push is a claim that this is done.
bash tools/ci/check-ownership.sh          # you touched only your own tree
bash tools/ci/check-secrets.sh            # no credentials, no real personal data
<your own test command>                   # your brief's §7 suite, green

# 5. Push when done with your changes, and open the PR.
git push -u origin db/phase0-schema-and-seed
gh pr create --base main --fill --title "db: Phase Zero schema, seed, and reader"

# 6. Lead agent reviews. Address feedback on the SAME branch — never a second one.
git push origin db/phase0-schema-and-seed

# 7. After the lead agent squash-merges, delete the branch to free your slot.
git push origin --delete db/phase0-schema-and-seed
git checkout main && git pull --ff-only origin main
git branch -d db/phase0-schema-and-seed
```

Step 4 is not optional. "Done with my changes" means tests pass, so a push with a red suite is a process
violation even when the code is later fixed.

## 4. Commit and PR rules

- Commit subject: `<prefix-word>: <imperative summary>` where the prefix word is `db`, `be`, `fe`, or
  `lead`. Keep it under 70 characters; detail goes in the body.
- Commits are small and each leaves the tree in a state the specialist's own tests can run on.
- Never `--amend` a commit that is already pushed. Never force-push a branch under review — the lead
  agent is reading it.
- The PR description states: which brief section it satisfies, which acceptance criteria in the brief's
  §7 now pass, which do not and why, every assumption added to `ASSUMPTIONS.md`, and every dependency
  added with its pinned version.
- A PR that touches a path outside the specialist's allowed list is **closed, not fixed in review**. The
  boundary is the point.
- Merges to `main` are **squash merges**, so one branch becomes one attributable commit and the
  one-branch rule stays legible in history.

## 5. Why conflicts should be impossible

Path ownership is disjoint by construction (`docs/00-ownership.md` §1), and no specialist may touch
`shared/`, `docs/`, or `tests/`. A merge conflict between two specialist branches therefore means a
boundary was crossed. Treat a conflict as a signal to investigate ownership, not as routine merge work to
resolve. The lead agent resolves it by rejecting the offending change, not by merging both sides.

Specialists rebase on `main` before opening a PR (`git pull --rebase origin main`) so the PR reflects
current `main`. Because the trees are disjoint, this pulls other specialists' code into the working tree
without touching the branch's own diff — which is exactly what integration testing needs, and is not
permission to read that code for assumptions (`docs/00-ownership.md` §3).

## 6. Hard prohibitions

- No push to `main`, and no force-push anywhere on the remote.
- No secrets, `.env` files, credentials, tokens, keys, or real personal data in any commit. `.env` is
  gitignored; if a secret is ever committed, stop and tell the lead agent — do not quietly rewrite
  history, because the secret is already exposed and must be rotated.
- No committing generated artifacts: `node_modules/`, `.next/`, `__pycache__/`, `.venv/`, build output,
  coverage reports, or database dumps.
- No `git config` changes to the shared repository.
- No merging your own pull request. The lead agent merges.
- No second branch, under any justification. See §2.

## 7. CI

Every pull request runs, in this order, and all must pass before the lead agent may merge:

1. `tools/ci/check-one-branch.sh` — the one-branch rule
2. `tools/ci/check-ownership.sh` — the branch changed only its owner's paths
3. `tools/ci/check-secrets.sh` — no credentials or personal-data patterns
4. the integrity guards from `docs/04-integrity-rules.md` that apply to the changed component
5. the changed component's own test suite

## 8. Repository

Remote: `origin` → https://github.com/akwsy/ryde-tribunal (private). `main` is pushed and is the default
branch. `gh` is authenticated as `akwsy`. GitHub Actions is enabled, so `guards` runs on every pull
request.

**`main` is NOT protected**, and cannot be on the current plan — branch protection and rulesets are both
paid features for private repositories (see D-20 in `docs/01-open-decisions.md`). The prohibitions in §6
are therefore convention backed by after-the-fact CI detection, not prevention. Treat them as binding
anyway: pushing to `main` or merging your own pull request is a process violation whether or not the
server stops you.
