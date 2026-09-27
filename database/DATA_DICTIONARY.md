# Data dictionary

## Schemas

- `ride_data`: queryable live ride, rider, driver, route, telemetry, fare, profile, scenario-tag, and generator-audit records. It may contain seeded synthetic rows and locally imported company rows in the same tables. It contains no outcome, verdict, fault, or expected-result columns.
- `case_archive`: historical synthetic dispute archive with advisory verdicts and human-review signals. Dispute IDs use the shared global `DSP-######` sequence; archive trip and party snapshot IDs remain namespaced and there are no foreign keys into `ride_data`.

## `ride_data`

- `users`: synthetic rider and driver principals (`USR-R-*`, `USR-D-*`).
- `user_profiles`: account age, total and completed rides, received-rating average, profile-level dispute-history outcomes, fraud flags, payment method, and driver vehicle details. The profile dispute-history columns are lifetime summary fields supplied with a company profile export; they are distinct from `user_dispute_counters`, which stores rolling-window and category counts used as scenario context.
- `user_rating_history`: historical rating points used for rating-pattern context.
- `ride_ratings`: one linked rating from each trip participant to the other; synthetic profile averages equal the mean rating received.
- `user_dispute_counters`: prior dispute counts by category for both roles.
- `rides`: live ride header, timestamps, status, quoted route/fare data.
- `ride_route_plans`: planned vs actual distances/durations, pickup/dropoff geography, no-show wait and arrival measurements.
- `ride_waypoints`: planned and actual route points.
- `ride_gps_samples`: ordered GPS samples with accuracy and collector metadata.
- `ride_stops`: stop locations, durations, and whether the rider requested the stop.
- `ride_chat_messages`: in-app chat records with participant role and timestamp.
- `ride_app_events`: ordered source-system app event timeline for each ride.
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
- `archive_user_snapshots`: archived party details with shared-format internal user IDs and bundle-local source keys.
- `archive_trip_snapshots`: self-contained archived trips with shared-format internal ride IDs, rider/driver snapshots, fare, pricing, GPS, and time fields.
- `archive_cases`: historical dispute headers (`DSP-######`), linked archive trip and filing-party snapshot IDs, and bundle-local case keys.
- `archive_case_classifications`: category, secondary labels, subject, monetary impact, and fraud-risk features.
- `archive_case_evidence`: archived evidence records and verification metadata, using shared-format `EV-######` IDs.
- `archive_case_decisions`: archived verdict, ruling type, recommended action, confidence, and decision origin.
- `archive_case_rulings`: separate model-proposed and reviewer-approved historical rulings.
- `archive_human_reviews`: human-review signal, changed fields, reason code, rationale, agreement, and reweighted evidence.
- `archive_appeals`: appeal metadata for a subset of historical cases.
- `archive_precedent_index`: searchable advisory precedent summaries and feature vectors.
