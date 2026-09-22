# Phase Zero data dictionary

## Schemas

- `ride_data`: live synthetic ride, rider, driver, route, telemetry, fare, profile, scenario-tag, and generator-audit records. It contains no outcome, verdict, fault, or expected-result columns.
- `case_archive`: historical synthetic dispute archive with advisory verdicts and human-review signals. It has disjoint identifiers and no foreign keys into `ride_data`.

## `ride_data`

- `users`: synthetic rider and driver principals (`USR-R-*`, `USR-D-*`).
- `user_profiles`: account age, lifetime rides, average rating, and rating trend.
- `user_rating_history`: historical rating points used for rating-pattern context.
- `user_dispute_counters`: prior dispute counts by category for both roles.
- `rides`: live ride header, timestamps, status, quoted route/fare data.
- `ride_route_plans`: planned vs actual distances/durations, pickup/dropoff geography, no-show wait and arrival measurements.
- `ride_waypoints`: planned and actual route points.
- `ride_gps_samples`: ordered GPS samples with accuracy and collector metadata.
- `ride_stops`: stop locations, durations, and whether the rider requested the stop.
- `ride_chat_messages`: in-app chat records with participant role and timestamp.
- `ride_call_attempts`: platform call attempts for no-show checks.
- `ride_fare_breakdowns`: fare ledger components, surge, cancellation fee, and total.
- `ride_fare_adjustments`: fare line adjustments such as tolls, airport fees, waiting charges, and rounding.
- `ride_promo_applications`: promo code and discount amount records.
- `ride_device_signals`: synthetic app/device records, including property-damage photo timing metadata.
- `ride_external_conditions`: synthetic traffic/weather/closure/event context.
- `scenario_tags`: coverage tags, including just-inside and just-outside policy threshold cases.
- `ingest_audit`: deterministic generator provenance and row counts.

## `case_archive`

- `archive_policy_versions`: synthetic policy-version metadata and JSON policy body.
- `archive_cases`: historical dispute headers (`DSP-ARCH-*`) and archive ride ids (`RIDE-ARCH-*`).
- `archive_case_classifications`: category, secondary labels, subject, monetary impact, and fraud-risk features.
- `archive_case_evidence`: archived evidence records and verification metadata.
- `archive_case_decisions`: archived verdict, ruling type, recommended action, confidence, and decision origin.
- `archive_human_reviews`: human-review signal, changed fields, reason code, rationale, agreement, and reweighted evidence.
- `archive_appeals`: appeal metadata for a subset of historical cases.
- `archive_precedent_index`: searchable advisory precedent summaries and feature vectors.
