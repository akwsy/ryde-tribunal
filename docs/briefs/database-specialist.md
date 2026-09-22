# Brief — Database specialist

Phase Zero. Read `docs/00-ownership.md`, `docs/02-api-contract.md` §5–6, and
`docs/04-integrity-rules.md` before writing anything.

## 1. Mission and scope

Build the PostgreSQL foundation for Ryde Tribunal: schema, migrations, a repeatable synthetic data
generator, documented read accessors, and tests. You own the data layer's correctness and its
**outcome-freedom**: the live ride data you produce must not contain the answers the tribunal is
supposed to derive.

Deliver:

1. Migrations creating the live ride/user schema and the **separate** historical dispute archive schema.
2. A deterministic generator producing **≥50 synthetic rides** and **≥30 synthetic historical dispute
   cases**, every row marked synthetic.
3. A Python read module implementing exactly the accessors in `docs/02-api-contract.md` §5, returning
   validated objects. **Eight accessors, all read-only — the module exposes no write surface.**
4. A PostgreSQL role for the backend with `SELECT` on your two schemas (`ride_data`, `case_archive`) and
   no `INSERT`, `UPDATE`, or `DELETE`, so read-only is enforced by the database rather than by review.
5. Tests proving the acceptance criteria in §8.

## 2. Non-goals

- You do not decide rulings, compute deviation percentages, or interpret policy.
- You do not write advocate or Judge logic, API routes, or UI.
- You do not create `case_*`, `model_work_*`, or `ruling_*` tables, and you provide **no write path** for
  them. Those live in the backend's own `tribunal` schema, migrated by the backend's own migration set.
  You own `ride_data` and `case_archive`, including the `archive_*` tables.
- You do not persist model work. `persist_model_work` appeared in draft v0.1.0 of the contract and has
  been removed — persisting advocate and Judge output is the backend's, writing the backend's tables.
  `ingest_audit` is your generator's own provenance record, not a landing zone for model output.
- You do not add outcome, verdict, fault, or expected-result columns to any live table. Ever.

## 3. Allowed paths

`database/**` — `database/migrations/`, `database/seed/`, `database/reader/`, `database/tests/`,
`database/README.md`, `database/ASSUMPTIONS.md`, `database/seed/policy/ryde-policy-0.1.0.json`.

## 4. Forbidden paths

`backend/**`, `frontend/**`, `shared/**`, `docs/**`, `tests/**`, `README.md`, `.env.example`.
Need a change there? File an integration request; do not edit.

## 5. Contracts

**Output — read accessors.** Exactly the eight accessors in `docs/02-api-contract.md` §5, with those
names and arguments. Each returns a Pydantic model; all timestamps UTC; all money as integer cents plus
currency. No accessor returns an outcome field for a live ride, and the module exposes no write function
of any kind.

**Output — identifiers.** `RIDE-%06d`, `USR-R-%06d`, `USR-D-%06d`, `EV-%06d` for live rows;
`RIDE-ARCH-%06d`, `DSP-ARCH-%06d` for archive rows. The two namespaces must never collide.

**Input.** The policy document `docs/03-mock-policy.md`, used **only** to place data around thresholds —
not to compute what the right answer would be.

**Required tables.** Live: `rides`, `ride_route_plans`, `ride_waypoints`, `ride_gps_samples`,
`ride_stops`, `ride_chat_messages`, `ride_call_attempts`, `ride_fare_breakdowns`,
`ride_fare_adjustments`, `ride_promo_applications`, `ride_device_signals`,
`ride_external_conditions`, `users`, `user_profiles`, `user_rating_history`, `user_dispute_counters`,
`scenario_tags`, `ingest_audit`. Archive: `archive_cases`, `archive_case_classifications`,
`archive_case_evidence`, `archive_case_decisions`, `archive_human_reviews`, `archive_appeals`,
`archive_policy_versions`, `archive_precedent_index`.

`archive_human_reviews` is required and must record whether a human reviewed, what they changed, an
override `reason_code` from the closed vocabulary in `docs/02-api-contract.md` §2, a specific rationale,
whether they agreed with the agent, and which evidence they reweighted. This signal is why the archive
exists — the Judge uses it to calibrate against its own decision-making.

## 6. Dependencies and assumptions

*Given:* PostgreSQL 16.15 is running locally on `:5432`; create database `ryde_tribunal` (D-13). No
Docker on this machine. Python 3.12 via `uv` (D-03). Alembic for migrations (D-01).

*You must assume and record in `database/ASSUMPTIONS.md`:* Singapore geography and SGD currency; a
~10-week ride window weighted to commute peaks; the archive spanning ~18 months across ≥3 policy
versions. Distribution targets: archive ~55% fully automated / ~45% human-touched.

*Ambiguous → ask, do not invent:* anything that would require encoding a correct outcome into live data.

## 7. Required tests

- Migrations apply to an empty database and roll back cleanly.
- **Outcome-freedom guard:** scan every live-table column name against
  `/expected|verdict|outcome|resolution|fault|ground.?truth|correct|is_valid|refund_granted/i` — zero
  matches. Fails the build.
- **Namespace disjointness:** no identifier value appears in both a live and an archive table.
- **No archive→live FK:** assert no foreign key from any `archive_*` table to any live table.
- ≥50 rides, ≥30 archive dispute cases, every row `synthetic = true`.
- Referential integrity: no orphaned case, ride, user, or evidence row; deleting a ride with dependents
  is rejected.
- Route data supports deviation, unexpected-stop, and duration comparison for every ride.
- Chat logs retain timestamp and participant role; no real personal data (a name/phone/email regex scan
  must find nothing).
- Fare data supports breakdown, surge, promo, and cancellation-fee checks.
- Profiles carry account age, rating pattern, and prior dispute counts for both roles.
- Archive cases carry classification, subject, verdict, recommended action, confidence where available,
  decision origin, and human-review records.
- **Boundary coverage:** for each numeric threshold in `docs/03-mock-policy.md` (15% deviation, 4-minute
  stop, 5-minute wait, 100 m arrival, 130% duration, 2-hour photo window) at least one ride sits just
  inside and one just outside. A test enumerates them by `scenario_tags`.
- Seed is repeatable: same seed → byte-identical dataset. Seed `ride-data-v1` /
  `case-archive-v1`, overridable by env.
- Every accessor returns a validated model and rejects a malformed row rather than coercing it.
- **No write surface:** the reader module exports no function that inserts, updates, or deletes, and a
  test connecting as the backend role proves `INSERT` into `ride_data` and `case_archive` is refused by
  PostgreSQL.

## 8. Passing criteria

All §7 tests pass; `database/README.md` documents setup, migration, seed, reseed, and each accessor with
an example; the outcome-freedom and disjointness guards are wired so a future contributor cannot
regress them silently; `ASSUMPTIONS.md` lists every assumption you made.

## 9. Handoff artifacts

`database/README.md` (run instructions), `database/ASSUMPTIONS.md`, the migration set, the generator with
its seed, the reader module, a `pytest` run log, a one-page data dictionary, and a dependency list with
pinned versions. Report to the lead agent; do not integrate with the backend yourself.

## 10. Git and GitHub

Read `docs/06-git-workflow.md` in full. It is binding. The owner-set rules that apply to you:

- **Your branch prefix is `db/`.** Branch from `main`, never from another specialist's branch.
- **You hold at most one branch at a time** — one in existence, not one in progress. Your previous
  branch must be merged and deleted on the remote *and* locally before you cut the next one. No second
  branch to park work or try an alternative; if the work does not fit one branch, say so and the section
  gets split.
- **Push to GitHub when you are done with your changes**, then open a pull request against `main`. A push
  is a claim the work is done, so `bash tools/ci/check-ownership.sh`, `bash tools/ci/check-secrets.sh`,
  `bash tools/ci/check-one-branch.sh` and your §7 test suite must all be green first.
- Address review feedback on the **same** branch. Never force-push a branch under review.
- After the lead agent squash-merges, delete the branch to free your slot.
- You do not merge your own pull request.

Your diff must stay inside `database/`. `tools/ci/check-ownership.sh` enforces it, and a pull request
that reaches outside your tree is closed rather than fixed in review. Because paths are disjoint, a merge
conflict means a boundary was crossed — report it, do not resolve it.

Commit subjects use the `db:` prefix, e.g. `db: add archive human-review records with reason codes`.
