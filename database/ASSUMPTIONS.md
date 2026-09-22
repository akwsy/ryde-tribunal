# Database assumptions

These are the non-obvious assumptions used for the Phase Zero database deliverable.

## Fixed by project documents

- Currency is `SGD` and every monetary value is stored as integer cents plus a currency code.
- All timestamps are UTC in the database and reader models.
- Live identifiers use `RIDE-%06d`, `USR-R-%06d`, `USR-D-%06d`, and `EV-%06d`.
- Archive identifiers use `RIDE-ARCH-%06d` and `DSP-ARCH-%06d`; archive evidence uses `ARCH-EV-*` to avoid collision with live evidence ids.
- The database specialist owns PostgreSQL schemas `ride_data` and `case_archive` only.
- The backend reads through a PostgreSQL role named `ryde_backend_readonly`, which has `SELECT` only on both database-owned schemas.
- `ingest_audit` records synthetic generator provenance only. It is not a landing zone for advocate or Judge output.

## Synthetic geography

All geography is synthetic and constrained to Singapore-area landmarks. The generator uses these labels as its fixed landmark set:

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
- `ryde-policy-0.1.0`

The policy text in all versions is synthetic. The Phase Zero runtime source of truth remains `database/seed/policy/ryde-policy-0.1.0.json`.

## Accessor boundary

`get_case(case_id)` returns case archive records from `case_archive.archive_cases`. Live tribunal cases, model work, rulings, and case history are backend-owned in the backend's `tribunal` schema and are not created or written by this package.
