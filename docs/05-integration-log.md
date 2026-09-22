# 05 — Integration log

Every change to `shared/` and every cross-component decision is recorded here by the lead agent. A
specialist requests an entry; it never writes one.

Format:

```
## YYYY-MM-DD — <short title>
- Requested by: <specialist>
- Reason:
- Components affected:
- Contract change: <none | shared/openapi.yaml v0.1.0 -> v0.1.1 | ...>
- Decision:
- Tests updated:
```

## 2026-09-22 — Repository and contract baseline
- Requested by: lead agent
- Reason: Phase Zero foundation — ownership boundaries, contracts, policy, integrity rules, briefs.
- Components affected: all.
- Contract change: `docs/02-api-contract.md` draft v0.1.0 authored. `shared/openapi.yaml` **not yet
  generated** — it is frozen from this document once the open decisions in `docs/01-open-decisions.md`
  are approved.
- Decision: no specialist is dispatched until the blocking decisions D-01, D-02, D-03, D-04, D-07 and
  D-12 are resolved by the project owner.
- Tests updated: none yet; `tests/` cross-component suite is authored after the gate clears.

## 2026-09-22 — Git workflow: push-when-done, one branch per specialist
- Requested by: project owner.
- Reason: owner rule — every specialist pushes to GitHub whenever its changes are done, and each may hold
  at most one branch at a time.
- Components affected: all three specialists, plus new lead-owned `tools/ci/` and `.github/`.
- Contract change: none to `shared/`. New `docs/06-git-workflow.md`; a §10 "Git and GitHub" section added
  to all three briefs; `docs/00-ownership.md` gains `tools/` and `.github/` and a new §6 on enforcement.
- Decision: the rule is enforced mechanically rather than by instruction. Each specialist owns a branch
  prefix (`db/`, `be/`, `fe/`, `lead/`); `tools/ci/check-one-branch.sh` fails when a prefix holds more
  than one remote branch or when a branch has no recognized prefix;
  `tools/ci/check-ownership.sh` fails a branch whose diff leaves its owner's tree;
  `tools/ci/check-secrets.sh` scans changed files for credential and real-personal-data patterns. All
  three run in `.github/workflows/guards.yml` on every pull request. Merges are squash merges so one
  branch becomes one attributable commit. Specialists do not merge their own pull requests.
- Consequence: a GitHub remote and branch protection are now **blocking** for all three specialists —
  recorded as D-19 and D-20. A specialist cannot satisfy "push when done" with no remote.
- Tests updated: three guard scripts added; syntax-checked and dry-run locally. They exercise for real on
  the first pull request, since `check-one-branch.sh` requires a remote.
