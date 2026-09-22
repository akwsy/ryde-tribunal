# 00 — Repository ownership and file boundaries

Authoritative. A specialist that needs to change something outside its own tree files an
integration request instead of editing it.

## 1. Ownership map

| Path | Owner | Others may |
|---|---|---|
| `database/` | Database specialist | read |
| `backend/` | Backend/model specialist | read |
| `frontend/` | Frontend specialist | read |
| `shared/` | Lead agent | read only |
| `docs/` | Lead agent | read only |
| `tests/` | Lead agent | read; add cases only via integration request |
| `tools/` | Lead agent | read; **run** the CI guards locally, never edit them |
| `.github/` | Lead agent | read only |
| `.env.example` | Lead agent | read only |
| `README.md` | Lead agent | read only |

"Read" means read for contract conformance. Reading another specialist's source to copy its
assumptions is forbidden — see §3.

## 2. Shared surface

`shared/` holds only artifacts the lead agent has approved as contracts:

- `shared/openapi.yaml` — the HTTP contract, generated from `docs/02-api-contract.md` and frozen per phase
- `shared/schemas/*.json` — JSON Schema for every payload crossing a component boundary
- `shared/fixtures/*.json` — contract fixtures both sides test against

A change to `shared/` requires an explicit integration decision recorded in
`docs/05-integration-log.md` with the reason, the affected components, and the new version. Nobody
edits `shared/` directly.

## 3. Independence rules

1. A specialist must **not** alter its output to accommodate another specialist's implementation. If
   the other side's behaviour conflicts with the contract, the contract is wrong or the other side is
   wrong — raise it, do not absorb it.
2. A specialist must **not** copy another specialist's assumptions. Everything it relies on comes from
   `docs/` or `shared/`, and anything it assumes beyond that is written into its own
   `ASSUMPTIONS.md` and flagged in its handoff.
3. A specialist must **not** take over another specialist's scope. The backend does not write
   migrations. The frontend does not query PostgreSQL. The database does not decide rulings.
4. Where a requirement is ambiguous and the behaviour is material, the specialist **stops and asks**.
   Inventing material behaviour is a gate failure, not initiative.

## 4. Hard prohibitions, all specialists

- No secrets committed. `.env.example` carries names and shapes only, never values.
- No real personal data, real names, real phone numbers, real payment instruments, or scraped data.
- No dependency added without recording it in the specialist's brief handoff section.
- The frontend never opens a database connection. It talks to the backend API only.
- No component writes to a table it does not own (see the write matrix in `docs/02-api-contract.md`).

## 5. Integration

Integration is a separate review step performed by the lead agent, never by a specialist unilaterally.
Sequence per phase: each specialist passes its own acceptance tests against fixtures → lead agent runs
`tests/` cross-component suite → failures are attributed to a contract or to one component, never
"fixed" by mutual adjustment → gate report to the project owner.

## 6. How these boundaries are enforced

Ownership is not honour-system. Each specialist owns a branch prefix (`db/`, `be/`, `fe/`) and
`tools/ci/check-ownership.sh` fails any branch whose diff reaches outside its owner's tree. A pull
request that crosses a boundary is **closed, not fixed in review**. Because the trees are disjoint, a
merge conflict between two specialist branches means a boundary was crossed — it is a signal to
investigate ownership, not routine merge work.

Each specialist also holds at most one branch at a time, enforced by `tools/ci/check-one-branch.sh`.
The full git and GitHub procedure is `docs/06-git-workflow.md`.
