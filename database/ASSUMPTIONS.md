# Database assumptions

These record non-obvious data-layer assumptions. Historical choices remain here for context;
`database/README.md` describes current commands and schema behavior.

## Fixed by project documents

- Currency is `SGD` and every monetary value is stored as integer cents plus a currency code.
- All timestamps are UTC in the database and reader models.
- Live identifiers use `RIDE-%06d`, `USR-R-%06d`, `USR-D-%06d`, and `EV-%06d`.
- Archive snapshot identifiers use the normal per-entity formats and shared allocators: `USR-R-%06d` / `USR-D-%06d`, `RIDE-%06d`, `DSP-%06d`, and `EV-%06d`. Policy surrogate IDs use `POLICY-%06d`; policy-version natural keys remain `ryde-policy-*`.
- The database specialist owns PostgreSQL schemas `ride_data` and `case_archive` only.
- The backend reads through `ryde_backend_readonly`, which has `SELECT` only on database-owned schemas. The backend's writable DSN login must be a member of the NOLOGIN `ryde_backend_writer` group to allocate shared EV IDs; that group has schema usage and sequence usage only, with no table privileges.
- `ingest_audit` records synthetic generator provenance only. It is not a landing zone for advocate or Judge output.

## Generated synthetic geography

The synthetic generator uses approximate Singapore-area landmarks as route anchors. Imported trip geography is not restricted to these generated locations. The generator uses these labels as its fixed landmark set:

- `marina_bay`
- `orchard`
- `changi_airport`
- `jurong_east`
- `woodlands`
- `tampines`
- `sentosa`
- `punggol`

Coordinates are approximate synthetic anchors for route geometry, not records of real trips.

## Ride timing distribution

The live ride window spans 70 days ending at the fixed reference instant `2026-09-22T00:00:00Z`. To model commute weighting, each generated ride is assigned a deterministic pseudo-random hour with this formula:

- 62% probability: commute-peak hour selected from `07`, `08`, `17`, `18`, `19`.
- 38% probability: off-peak hour selected from `10`, `11`, `13`, `14`, `21`, `22`.
- Minute selection is deterministic from the same seed.

The fixed reference instant keeps reseeding byte-identical.

## Archive span and policy versions

The archive spans about 18 months before `2026-09-22T00:00:00Z` and uses three synthetic policy-version labels:

- `ryde-policy-0.0.8`
- `ryde-policy-0.0.9`
- `ryde-policy-1.0.0` for current adjudication; fictional 0.1.x versions remain preserved for historical cases.

Policy versions 0.1.x are fictional and preserved for historical records. The current runtime source of truth is `database/seed/policy/ryde-policy-1.0.0.json`.

## Accessor boundary

`get_archive_case(archive_case_id)` returns archive records from `case_archive.archive_cases` and fails closed if the same ID belongs to a live case. Live
disputes, model work, proposed rulings, reviewer-approved rulings, and case history are backend-owned
in the backend's `tribunal` schema and are not created by the company-data importer. The read module
exposes eleven validated accessors; the separate importer is an explicit write command limited to
company trip/profile/evidence rows in `ride_data`.

## Submission policy
Official policy 1.0.0 is additive. Historical seed generation continues to use fictional 0.1.2
to preserve prior decisions; submission data is separately generated and imported. Existing ride
headers and app-event payloads can carry the required factual timestamps without a schema migration.
No new dependency. Official sources are paraphrased, not treated as blanket refund authority.

Migration 0009 accepts actual Ryde service names without relabelling old tiers. Downgrade
removes the expanded check rather than deleting or relabelling source rows.
