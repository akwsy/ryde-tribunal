# Archived-case ZIP format v1

This is a separate synthetic-history import path. It never writes to `ride_data`; archive snapshots
are self-contained and have no foreign keys to live users or rides. Internal archive IDs are generated
by the application. CSV `source_*_key` fields are bundle-local link keys and are not database IDs.

The ZIP root contains `manifest.json` plus these six UTF-8 CSVs. Internal archive IDs use the normal
entity formats and shared allocators: `DSP-######` cases use `tribunal.case_id_seq`, `RIDE-######`
trips use `ride_data.imported_ride_id_seq`, `USR-R-######` / `USR-D-######` party snapshots use
their corresponding `ride_data` user sequences, and `EV-######` evidence uses
`ride_data.imported_evidence_id_seq`. Values supplied in the bundle's `source_*_key` fields are
retained as source references and are never used as internal IDs.

- `manifest.json`: `{"format_version":"1","source_system":"stable-source-name","synthetic":true}`.
- `users.csv`: `source_user_key,role,display_name,account_age_days,average_rating,total_trips`.
- `trips.csv`: `source_trip_key,rider_source_user_key,driver_source_user_key,trip_status,trip_at,requested_at,accepted_at,pickup_at,dropoff_at,service_tier,quoted_distance_meters,quoted_duration_seconds,quoted_fare_cents,fare_cents,currency,rider_rating,driver_rating,fare_breakdown,pricing_structure,pickup_details,dropoff_details,gps_data`. These rows preserve linked rider/driver snapshots, trip timing, quoted and actual fare, pricing/fare breakdown, pickup/dropoff, and GPS details. Completed trips require one rating in each direction; cancelled trips have neither. Structured fields contain valid JSON.
- `cases.csv`: `source_case_key,source_trip_key,filing_user_source_key,category,subject,filed_by,created_at,policy_version,primary_classification,secondary_classifications,monetary_impact_cents,fraud_risk`.
- `rulings.csv`: `source_case_key,stage,origin,verdict,ruling_type,action_description,amount_cents,currency,confidence,decided_at`. Every case has at least one recorded ruling. A `model_proposed`/`agent` row and an optional `reviewer_approved`/`human` row remain separate; a reviewer-only historical record is accepted when no model proposal was recorded.
- `reviews.csv`: `source_case_key,reason_code,rationale,agreed_with_agent,changed_fields,reweighted_evidence,reviewed_at`; exactly one row is required for each reviewer-approved ruling and none for other cases.
- `evidence.csv`: `source_evidence_key,source_case_key,evidence_class,source,recorded_at,provenance,verification,visibility,payload`. Every row must reference a case in this bundle. The evidence payload and its provenance, verification, timestamp, and visibility are retained in the archive.

The validator requires every case to reference a bundle trip and filer, requires the filed role to match
the filer, and requires filing time to be strictly later than the trip time. Supported categories are
the eight active filing categories. The archive import stores source keys with the manifest namespace,
does not overwrite existing rows, and returns a mapping of source keys to generated archive IDs.

```bash
cd database
uv run python -m archive_importer validate /path/to/archive.zip
uv run python -m archive_importer import /path/to/archive.zip
```
