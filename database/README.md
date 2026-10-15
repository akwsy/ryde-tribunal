# Ryde Tribunal database layer

Database implementation for the database-owned schemas `ride_data` and `case_archive`. The local
`ride_data` pool can contain both generated synthetic rows and company records imported for testing;
the two use the same queryable tables and standard app-generated internal IDs. Populated company
exports are local-only and must not be committed to Git.

## Guarantees

- Live ride data contains no outcome, verdict, fault, expected-result, resolution, ground-truth, correctness, validity, or refund-granted columns.
- Historical verdicts live only in `case_archive`; archive dispute, trip, rider/driver snapshot, and evidence IDs use the same per-entity formats and shared allocators as live/imported records.
- `case_archive` has no foreign keys to `ride_data`.
- The backend role `ryde_backend_readonly` receives `SELECT` on `ride_data` and `case_archive` and no write privileges.
- The reader module exposes eleven validated read accessors and no write surface. The separate ZIP importer is the database package's only company-data write path.

## Setup

From the repository root:

```bash
createdb ryde_tribunal  # safe to skip if it already exists
cd database
uv venv --python 3.12.14
uv pip install -r requirements.lock
```

If your PostgreSQL connection differs from the local default, set:

```bash
export DATABASE_URL="postgresql:///ryde_tribunal"
```

## Migrate

For a fresh database, upgrade both migration sets to `head`. For an existing database with archive
rows, use the staged sequence below so legacy IDs are remapped before the final constraints are
applied.

```bash
cd backend
uv run alembic -c alembic.ini upgrade head
cd ../database
uv run alembic -c alembic.ini upgrade 0007_global_archive_entity_ids
```

The backend migrations own `tribunal.case_id_seq`. Database revision 0007 prepares shared entity
allocators and temporary transition constraints. Keep `tribunal.evidence_id_seq` until the remap
records its high-water mark; retire it only after EV allocator cutover.

### One-time global internal ID normalization

Existing databases need a one-time transactional remap after backend migrations reach `head` and
database migrations reach revision 0007, before upgrading database migrations to `head`, and before
the app, seed generator, or importers are started. Stop the app and any import/seed process,
make a PostgreSQL backup, then run the preview from `database/` using a migration-capable account
(never `ryde_backend_readonly`):

```bash
cd database
DATABASE_URL='postgresql:///ryde_tribunal' uv run python ../tools/migrate_global_record_ids.py
```

Review the number of records and proposed ID ranges. The remap covers cases, archived ride and
rider/driver snapshots, evidence, and policy snapshot IDs. Each uses the same ordinary ID format as
other records of that type, without an `ARCH` marker. If the preview is correct, apply the remap:

```bash
DATABASE_URL='postgresql:///ryde_tribunal' uv run python ../tools/migrate_global_record_ids.py --apply
```

The lead-owned tool remaps live and archived case IDs into one globally unique filing-time-ordered
sequence, then remaps snapshot ride, user, evidence, and policy IDs to the ordinary per-entity
formats. It updates stored references and exact ID values in JSON/JSONB within `tribunal` and
`case_archive`, while leaving company-provided source IDs unchanged. A migration marker makes a
completed run idempotent. The default command is a dry run and commits nothing. After applying the
remap, finish the database migration to install constraints that reject the old `ARCH` formats:

```bash
cd database
uv run alembic -c alembic.ini upgrade head
```

Do not reseed or import between migrations and the remap. Keep `tribunal.evidence_id_seq` until the
tool has captured its high-water mark and completed the EV allocator handoff. PostgreSQL sequence increments are not transactional:
if an apply attempt fails after advancing a sequence, rows roll back but the sequence may remain
higher, creating harmless ID gaps on a later run. Any previously copied IDs in external notes or
exports will be stale after the remap; the tool can update references stored inside these two schemas
only.

The reviewer dashboard's archive history read requires the
`case_archive.archive_case_rulings` table, created by migration
`0005_archive_history` (file `0005_trip_ratings_and_archive_snapshots.py`). If the backend reports that this
relation is missing, stop the app and apply the pending migrations with the
database's migration-capable account, then restart the app. `upgrade head`
applies forward migrations and preserves existing rows; it is not a reset or
reseed. Do not use the `ryde_backend_readonly` account for migrations.

Rollback only a disposable database. This removes both schemas and all their rows.

```bash
cd database
uv run alembic -c alembic.ini downgrade base
```

## Seed or reseed

The generator is deterministic. Defaults are `RIDE_DATA_SEED=ride-data-v1` and `CASE_ARCHIVE_SEED=case-archive-v1`.

```bash
cd database
uv run python -m seed.generator
```

Override seeds:

```bash
RIDE_DATA_SEED=my-ride-seed CASE_ARCHIVE_SEED=my-archive-seed uv run python -m seed.generator
```

The generator creates 100 synthetic users (50 riders and 50 drivers), 160 synthetic rides, 47
synthetic archive cases, and linked rating snapshots. The additions are deterministic: 20 users,
100 rides, and 15 archive cases on top of the previous seed totals. Added rides and disputes are dated
within June 1–August 31, 2026; each added dispute follows its linked trip. Original seed dates remain
unchanged. Company rows are added separately and must never be removed by reseeding.

## Export synthetic test datasets

After migrating and seeding, create two separate ZIP bundles outside the repository. The first
contains user profiles, trips, fare breakdowns, GPS, and participant ratings in the company importer
format. The second contains self-contained archived trips, the people involved, dispute details, and
separate model-proposed and reviewer-approved rulings.

```bash
cd database
uv run python -m seed.export_bundles \
  --company-out /tmp/ryde-synthetic-users-trips.zip \
  --archive-out /tmp/ryde-synthetic-archive.zip
```

Validate/import the user and trip bundle with the existing company importer. Its manifest marks these
rows synthetic and the importer continues generating internal user/trip IDs:

```bash
uv run python -m importer validate /tmp/ryde-synthetic-users-trips.zip
uv run python -m importer import /tmp/ryde-synthetic-users-trips.zip
```

Archive history uses a separate ZIP importer and writes only to `case_archive`:

```bash
uv run python -m archive_importer validate /tmp/ryde-synthetic-archive.zip
uv run python -m archive_importer import /tmp/ryde-synthetic-archive.zip
```

The backend migrations own `tribunal.case_id_seq`. Apply backend migrations before seeding or
importing archive cases. Live filing, archive seeding, and archive import all allocate from this
same sequence. The database package intentionally has no runtime fallback sequence; its DB-only
test fixture provisions a sequence only in its disposable test database.

Both importers append, skip already mapped archive IDs or company IDs, and print app-generated ID
mappings. Keep generated bundles and mapping outputs outside Git if they are not committed as
synthetic examples.

## Import company CSV ZIPs

After migrating, validate and import a ZIP bundle using the `database/importer/FORMAT.md` contract.
The importer only appends new company IDs; existing company user/trip IDs are reported and reused
for linking, with their stored rows left unchanged. The mapping output contains company IDs and
generated internal IDs only.

```bash
cd database
uv run python -m importer validate /path/to/company-export.zip
uv run python -m importer import /path/to/company-export.zip --mapping-out /path/to/company-id-mapping.csv
```

Set `DATABASE_URL` if the target database is not the local `ryde_tribunal` default. Keep both the
company ZIP and mapping output outside Git; do not commit populated company data.

### Dedicated importer database login

The app's CSV ZIP upload endpoint uses a separate `IMPORT_DATABASE_DSN`. Do not point it at the
read-only `ryde_backend_readonly` account. Provision a dedicated append-only role once per target
database, using a PostgreSQL administrator account:

```bash
psql -d ryde_tribunal -f database/roles/provision_import_role.sql
psql -d ryde_tribunal
```

At the `psql` prompt, set a local password without putting it in shell history:

```text
\password ryde_data_importer
```

Then put a URL for this role in the local, untracked backend `.env` file, for example:
`IMPORT_DATABASE_DSN=postgresql://ryde_data_importer:<your-password>@localhost:5432/ryde_tribunal`.
Keep the password out of Git and do not reuse the administrator or read-only role. If your database
has a different name, connect to that database and change the `GRANT CONNECT ON DATABASE` statement
in the provisioning SQL before running it.

The role can connect, read company-ID maps for duplicate checks, read only `user_id` and `role` from
`ride_data.users`, append to the specific tables used by the importer, and advance only its four
internal-ID sequences. It cannot update or delete rows, alter schemas, create roles/databases, or
access archive tables. The existing `ryde_backend_readonly` role remains SELECT-only. Import calls
serialize duplicate checks with a transaction-scoped advisory lock.

## Run tests

The suite migrates and seeds `RYDE_TEST_DATABASE_URL`, which defaults to
`postgresql:///ryde_tribunal_test`, and creates/drops temporary databases through
`POSTGRES_ADMIN_URL`. The fixture rejects database names that do not end in `_test` or `_tests`.
It does not use the app's `DATABASE_URL` or load a project `.env` file. Keep this target disposable;
the test suite reseeds its database.

```bash
cd database
export RYDE_TEST_DATABASE_URL="postgresql:///ryde_tribunal_test"
export POSTGRES_ADMIN_URL="postgresql:///postgres"
uv run pytest -q
```

The suite covers migration apply/rollback, outcome-freedom, canonical per-entity ID formats and collision-free live/archive allocations, absence of archive-to-live foreign keys, synthetic row counts, referential integrity, route/fare/chat/profile/archive completeness, threshold boundary coverage, seed repeatability and export mapping stability, mixed-data reseeding, CSV ZIP validation/import, read-accessor validation (including trip search), and read-only backend-role enforcement.

## Read accessors

Import from `reader`:

```python
from reader import (
    get_archive_case,
    list_archive_disputes,
    get_app_events,
    get_chat_log,
    get_fare_breakdown,
    get_gps_samples,
    get_profile,
    get_ride,
    get_route,
    search_archive,
    search_rides,
)
```

Examples:

```python
ride = get_ride("RIDE-000001")
route = get_route("RIDE-000001")
gps = get_gps_samples("RIDE-000001")
chat = get_chat_log("RIDE-000001")
fare = get_fare_breakdown("RIDE-000001")
rider = get_profile("USR-R-000001")
archive_cases = list_archive_disputes(limit=200)
archive_case = get_archive_case(archive_cases[0].archive_case_id)
app_events = get_app_events("RIDE-000001")
precedents = search_archive("route_deviation", {"category": "route_deviation"}, 5)
trip_choices = search_rides("Joo Chiat", limit=20)
```

All return strict Pydantic models. Malformed rows are rejected rather than coerced.
Pass `limit=None` only for internal dashboard aggregation that must include the complete archive;
bounded API listings should always provide a positive limit.

## Backend read-only role

The migration creates `ryde_backend_readonly` with a local development password. It has `USAGE` and `SELECT` on `ride_data` and `case_archive`, and no `INSERT`, `UPDATE`, or `DELETE`.

Migration `0007_global_archive_entity_ids` also creates the NOLOGIN group `ryde_backend_writer` if
needed and gives it only `USAGE` on the `ride_data` schema and shared evidence ID sequence. The login
used by `TRIBUNAL_DATABASE_DSN` must be granted membership by the database administrator, for
example `GRANT ryde_backend_writer TO app_writer_login;`. The login must inherit the group grant
(the backend does not issue `SET ROLE`). If the group already exists, the migration preserves its
LOGIN/INHERIT attributes and adds only the narrow grants. This does not grant it access to ride data
tables. The migration also enables `ON UPDATE CASCADE` on archive-schema foreign keys so the
cross-schema ID remap can update archive identifiers without breaking their references.

For tests that connect as the role:

```bash
export BACKEND_READONLY_DATABASE_URL="postgresql://ryde_backend_readonly:ryde_backend_readonly@localhost:5432/ryde_tribunal"
```
