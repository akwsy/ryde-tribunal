"""create phase zero ride and archive schemas

Revision ID: 0001_phase0_schema
Revises:
Create Date: 2026-09-22 00:00:00 UTC
"""
from __future__ import annotations

from alembic import op

revision = "0001_phase0_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ride_data")
    op.execute("CREATE SCHEMA IF NOT EXISTS case_archive")

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ryde_backend_readonly') THEN
            CREATE ROLE ryde_backend_readonly LOGIN PASSWORD 'ryde_backend_readonly' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE TABLE ride_data.users (
          user_id text PRIMARY KEY,
          role text NOT NULL CHECK (role IN ('rider', 'driver')),
          display_handle text NOT NULL,
          created_at timestamptz NOT NULL,
          account_status text NOT NULL CHECK (account_status IN ('active', 'restricted', 'closed')),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          CONSTRAINT users_id_shape CHECK (
            (role = 'rider' AND user_id ~ '^USR-R-[0-9]{6}$') OR
            (role = 'driver' AND user_id ~ '^USR-D-[0-9]{6}$')
          )
        );

        CREATE TABLE ride_data.user_profiles (
          user_id text PRIMARY KEY REFERENCES ride_data.users(user_id) ON DELETE RESTRICT,
          account_age_days integer NOT NULL CHECK (account_age_days >= 0),
          lifetime_completed_rides integer NOT NULL CHECK (lifetime_completed_rides >= 0),
          average_rating numeric(3,2) NOT NULL CHECK (average_rating >= 1 AND average_rating <= 5),
          rating_trend text NOT NULL CHECK (rating_trend IN ('stable', 'rising', 'falling', 'volatile')),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.user_rating_history (
          rating_id bigserial PRIMARY KEY,
          user_id text NOT NULL REFERENCES ride_data.users(user_id) ON DELETE RESTRICT,
          rating_at timestamptz NOT NULL,
          rating numeric(3,2) NOT NULL CHECK (rating >= 1 AND rating <= 5),
          sample_size integer NOT NULL CHECK (sample_size > 0),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.user_dispute_counters (
          user_id text PRIMARY KEY REFERENCES ride_data.users(user_id) ON DELETE RESTRICT,
          disputes_30d integer NOT NULL CHECK (disputes_30d >= 0),
          disputes_180d integer NOT NULL CHECK (disputes_180d >= 0),
          route_deviation_count integer NOT NULL CHECK (route_deviation_count >= 0),
          no_show_count integer NOT NULL CHECK (no_show_count >= 0),
          property_damage_count integer NOT NULL CHECK (property_damage_count >= 0),
          safety_incident_count integer NOT NULL CHECK (safety_incident_count >= 0),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.rides (
          ride_id text PRIMARY KEY CHECK (ride_id ~ '^RIDE-[0-9]{6}$'),
          rider_user_id text NOT NULL REFERENCES ride_data.users(user_id) ON DELETE RESTRICT,
          driver_user_id text NOT NULL REFERENCES ride_data.users(user_id) ON DELETE RESTRICT,
          requested_at timestamptz NOT NULL,
          accepted_at timestamptz,
          pickup_at timestamptz,
          dropoff_at timestamptz,
          ride_status text NOT NULL CHECK (ride_status IN ('completed', 'cancelled_after_arrival', 'cancelled_before_assignment')),
          service_tier text NOT NULL CHECK (service_tier IN ('standard', 'premium', 'assist')),
          quoted_distance_meters integer NOT NULL CHECK (quoted_distance_meters > 0),
          quoted_duration_seconds integer NOT NULL CHECK (quoted_duration_seconds > 0),
          quoted_fare_cents integer NOT NULL CHECK (quoted_fare_cents >= 0),
          currency char(3) NOT NULL DEFAULT 'SGD',
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          CONSTRAINT ride_time_order CHECK (accepted_at IS NULL OR accepted_at >= requested_at),
          CONSTRAINT ride_pickup_order CHECK (pickup_at IS NULL OR accepted_at IS NULL OR pickup_at >= accepted_at),
          CONSTRAINT ride_dropoff_order CHECK (dropoff_at IS NULL OR pickup_at IS NULL OR dropoff_at >= pickup_at)
        );

        CREATE TABLE ride_data.ride_route_plans (
          ride_id text PRIMARY KEY REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          pickup_label text NOT NULL,
          pickup_lat numeric(9,6) NOT NULL,
          pickup_lon numeric(9,6) NOT NULL,
          dropoff_label text NOT NULL,
          dropoff_lat numeric(9,6) NOT NULL,
          dropoff_lon numeric(9,6) NOT NULL,
          planned_distance_meters integer NOT NULL CHECK (planned_distance_meters > 0),
          actual_distance_meters integer NOT NULL CHECK (actual_distance_meters > 0),
          planned_duration_seconds integer NOT NULL CHECK (planned_duration_seconds > 0),
          actual_duration_seconds integer NOT NULL CHECK (actual_duration_seconds > 0),
          driver_arrival_distance_meters integer CHECK (driver_arrival_distance_meters >= 0),
          driver_wait_seconds integer CHECK (driver_wait_seconds >= 0),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.ride_waypoints (
          waypoint_id bigserial PRIMARY KEY,
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          route_kind text NOT NULL CHECK (route_kind IN ('planned', 'actual')),
          sequence_no integer NOT NULL CHECK (sequence_no >= 0),
          lat numeric(9,6) NOT NULL,
          lon numeric(9,6) NOT NULL,
          label text NOT NULL,
          recorded_at timestamptz,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          UNIQUE (ride_id, route_kind, sequence_no)
        );

        CREATE TABLE ride_data.ride_gps_samples (
          sample_id bigserial PRIMARY KEY,
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          sample_at timestamptz NOT NULL,
          lat numeric(9,6) NOT NULL,
          lon numeric(9,6) NOT NULL,
          accuracy_meters numeric(6,2) NOT NULL CHECK (accuracy_meters >= 0),
          speed_meters_per_second numeric(6,2) NOT NULL CHECK (speed_meters_per_second >= 0),
          collector text NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.ride_stops (
          stop_id bigserial PRIMARY KEY,
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          started_at timestamptz NOT NULL,
          ended_at timestamptz NOT NULL,
          duration_seconds integer NOT NULL CHECK (duration_seconds >= 0),
          lat numeric(9,6) NOT NULL,
          lon numeric(9,6) NOT NULL,
          rider_requested boolean NOT NULL,
          note text NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          CHECK (ended_at >= started_at)
        );

        CREATE TABLE ride_data.ride_chat_messages (
          message_id text PRIMARY KEY CHECK (message_id ~ '^EV-[0-9]{6}$'),
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          participant_role text NOT NULL CHECK (participant_role IN ('rider', 'driver', 'support')),
          sent_at timestamptz NOT NULL,
          message_text text NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.ride_call_attempts (
          call_id text PRIMARY KEY CHECK (call_id ~ '^EV-[0-9]{6}$'),
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          caller_role text NOT NULL CHECK (caller_role IN ('rider', 'driver', 'support')),
          recipient_role text NOT NULL CHECK (recipient_role IN ('rider', 'driver', 'support')),
          attempted_at timestamptz NOT NULL,
          call_status text NOT NULL CHECK (call_status IN ('answered', 'unanswered', 'missed')),
          duration_seconds integer NOT NULL CHECK (duration_seconds >= 0),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.ride_fare_breakdowns (
          fare_id bigserial PRIMARY KEY,
          ride_id text NOT NULL UNIQUE REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          base_fare_cents integer NOT NULL CHECK (base_fare_cents >= 0),
          distance_fare_cents integer NOT NULL CHECK (distance_fare_cents >= 0),
          time_fare_cents integer NOT NULL CHECK (time_fare_cents >= 0),
          waiting_fare_cents integer NOT NULL CHECK (waiting_fare_cents >= 0),
          surge_multiplier numeric(4,2) NOT NULL CHECK (surge_multiplier >= 1),
          surge_fare_cents integer NOT NULL CHECK (surge_fare_cents >= 0),
          cancellation_fee_cents integer NOT NULL CHECK (cancellation_fee_cents >= 0),
          platform_fee_cents integer NOT NULL CHECK (platform_fee_cents >= 0),
          total_fare_cents integer NOT NULL CHECK (total_fare_cents >= 0),
          currency char(3) NOT NULL DEFAULT 'SGD',
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.ride_fare_adjustments (
          adjustment_id bigserial PRIMARY KEY,
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          adjustment_type text NOT NULL CHECK (adjustment_type IN ('toll', 'airport_fee', 'waiting_charge', 'rounding')),
          amount_cents integer NOT NULL,
          currency char(3) NOT NULL DEFAULT 'SGD',
          applied_at timestamptz NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.ride_promo_applications (
          promo_id bigserial PRIMARY KEY,
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          promo_code text NOT NULL,
          amount_cents integer NOT NULL CHECK (amount_cents >= 0),
          currency char(3) NOT NULL DEFAULT 'SGD',
          applied_at timestamptz NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.ride_device_signals (
          signal_id text PRIMARY KEY CHECK (signal_id ~ '^EV-[0-9]{6}$'),
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          user_id text REFERENCES ride_data.users(user_id) ON DELETE RESTRICT,
          signal_type text NOT NULL CHECK (signal_type IN ('app_open', 'pickup_pin_set', 'damage_photo', 'battery_state')),
          recorded_at timestamptz NOT NULL,
          payload jsonb NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.ride_external_conditions (
          condition_id bigserial PRIMARY KEY,
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          condition_type text NOT NULL CHECK (condition_type IN ('traffic', 'weather', 'road_closure', 'event')),
          observed_at timestamptz NOT NULL,
          source_label text NOT NULL,
          payload jsonb NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE ride_data.scenario_tags (
          tag_id bigserial PRIMARY KEY,
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          tag text NOT NULL,
          threshold_name text,
          side text CHECK (side IN ('inside', 'outside', 'coverage', 'baseline')),
          observed_value numeric(12,3),
          threshold_value numeric(12,3),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          UNIQUE (ride_id, tag)
        );

        CREATE TABLE ride_data.ingest_audit (
          audit_id bigserial PRIMARY KEY,
          generator_name text NOT NULL,
          ride_seed text NOT NULL,
          archive_seed text NOT NULL,
          generated_at timestamptz NOT NULL,
          policy_version text NOT NULL,
          row_counts jsonb NOT NULL,
          dataset_sha256 text NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE case_archive.archive_policy_versions (
          policy_version text PRIMARY KEY,
          policy_version_id text NOT NULL UNIQUE,
          effective_from timestamptz NOT NULL,
          effective_to timestamptz,
          policy_document jsonb NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE case_archive.archive_cases (
          archive_case_id text PRIMARY KEY CHECK (archive_case_id ~ '^DSP-ARCH-[0-9]{6}$'),
          archive_ride_id text NOT NULL UNIQUE CHECK (archive_ride_id ~ '^RIDE-ARCH-[0-9]{6}$'),
          category text NOT NULL CHECK (category IN ('route_deviation', 'no_show', 'property_damage', 'safety_incident')),
          subject text NOT NULL,
          filed_by text NOT NULL CHECK (filed_by IN ('rider', 'driver')),
          created_at timestamptz NOT NULL,
          policy_version text NOT NULL REFERENCES case_archive.archive_policy_versions(policy_version) ON DELETE RESTRICT,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE case_archive.archive_case_classifications (
          archive_case_id text PRIMARY KEY REFERENCES case_archive.archive_cases(archive_case_id) ON DELETE RESTRICT,
          primary_classification text NOT NULL,
          secondary_classifications jsonb NOT NULL,
          subject text NOT NULL,
          monetary_impact_cents integer NOT NULL CHECK (monetary_impact_cents >= 0),
          fraud_risk numeric(4,3) NOT NULL CHECK (fraud_risk >= 0 AND fraud_risk <= 1),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE case_archive.archive_case_evidence (
          archive_evidence_id text PRIMARY KEY,
          archive_case_id text NOT NULL REFERENCES case_archive.archive_cases(archive_case_id) ON DELETE RESTRICT,
          evidence_class text NOT NULL CHECK (evidence_class IN ('gps_telemetry', 'chat_log', 'fare', 'profile_history', 'attachment', 'external')),
          source text NOT NULL CHECK (source IN ('system_record', 'rider_submitted', 'driver_submitted', 'external')),
          recorded_at timestamptz NOT NULL,
          provenance jsonb NOT NULL,
          verification jsonb NOT NULL,
          visibility text NOT NULL CHECK (visibility IN ('both', 'rider_only', 'driver_only', 'reviewer_only')),
          payload jsonb NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE case_archive.archive_case_decisions (
          archive_case_id text PRIMARY KEY REFERENCES case_archive.archive_cases(archive_case_id) ON DELETE RESTRICT,
          verdict text NOT NULL CHECK (verdict IN ('refund', 'compensation', 'no_action', 'escalated')),
          ruling_type text NOT NULL CHECK (ruling_type IN ('refund', 'compensation', 'no_action')),
          recommended_action_description text NOT NULL,
          recommended_amount_cents integer NOT NULL CHECK (recommended_amount_cents >= 0),
          currency char(3) NOT NULL DEFAULT 'SGD',
          confidence numeric(4,3) CHECK (confidence >= 0 AND confidence <= 1),
          decision_origin text NOT NULL CHECK (decision_origin IN ('agent', 'human')),
          decided_at timestamptz NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE case_archive.archive_human_reviews (
          review_id bigserial PRIMARY KEY,
          archive_case_id text NOT NULL UNIQUE REFERENCES case_archive.archive_cases(archive_case_id) ON DELETE RESTRICT,
          human_reviewed boolean NOT NULL,
          changed_fields jsonb NOT NULL,
          reason_code text CHECK (reason_code IN ('policy_misapplied', 'evidence_misweighted', 'evidence_missing', 'fraud_suspected', 'goodwill', 'safety_override', 'other')),
          rationale text NOT NULL,
          agreed_with_agent boolean,
          reweighted_evidence jsonb NOT NULL,
          reviewed_at timestamptz,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          CHECK ((human_reviewed IS TRUE AND reason_code IS NOT NULL AND reviewed_at IS NOT NULL) OR (human_reviewed IS FALSE AND reason_code IS NULL))
        );

        CREATE TABLE case_archive.archive_appeals (
          appeal_id bigserial PRIMARY KEY,
          archive_case_id text NOT NULL REFERENCES case_archive.archive_cases(archive_case_id) ON DELETE RESTRICT,
          appealed_at timestamptz NOT NULL,
          appeal_reason text NOT NULL,
          appeal_status text NOT NULL CHECK (appeal_status IN ('submitted', 'reviewed', 'closed')),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );

        CREATE TABLE case_archive.archive_precedent_index (
          precedent_id bigserial PRIMARY KEY,
          archive_case_id text NOT NULL REFERENCES case_archive.archive_cases(archive_case_id) ON DELETE RESTRICT,
          category text NOT NULL,
          feature_vector jsonb NOT NULL,
          summary text NOT NULL,
          policy_version text NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          UNIQUE (archive_case_id)
        );
        """
    )

    op.execute(
        """
        GRANT USAGE ON SCHEMA ride_data, case_archive TO ryde_backend_readonly;
        GRANT SELECT ON ALL TABLES IN SCHEMA ride_data TO ryde_backend_readonly;
        GRANT SELECT ON ALL TABLES IN SCHEMA case_archive TO ryde_backend_readonly;
        ALTER DEFAULT PRIVILEGES IN SCHEMA ride_data GRANT SELECT ON TABLES TO ryde_backend_readonly;
        ALTER DEFAULT PRIVILEGES IN SCHEMA case_archive GRANT SELECT ON TABLES TO ryde_backend_readonly;
        REVOKE CREATE ON SCHEMA ride_data FROM PUBLIC;
        REVOKE CREATE ON SCHEMA case_archive FROM PUBLIC;
        REVOKE CREATE ON SCHEMA ride_data FROM ryde_backend_readonly;
        REVOKE CREATE ON SCHEMA case_archive FROM ryde_backend_readonly;
        """
    )


def downgrade() -> None:
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA ride_data FROM ryde_backend_readonly")
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA case_archive FROM ryde_backend_readonly")
    op.execute("REVOKE ALL PRIVILEGES ON SCHEMA ride_data FROM ryde_backend_readonly")
    op.execute("REVOKE ALL PRIVILEGES ON SCHEMA case_archive FROM ryde_backend_readonly")
    op.execute("DROP TABLE IF EXISTS case_archive.archive_precedent_index")
    op.execute("DROP TABLE IF EXISTS case_archive.archive_appeals")
    op.execute("DROP TABLE IF EXISTS case_archive.archive_human_reviews")
    op.execute("DROP TABLE IF EXISTS case_archive.archive_case_decisions")
    op.execute("DROP TABLE IF EXISTS case_archive.archive_case_evidence")
    op.execute("DROP TABLE IF EXISTS case_archive.archive_case_classifications")
    op.execute("DROP TABLE IF EXISTS case_archive.archive_cases")
    op.execute("DROP TABLE IF EXISTS case_archive.archive_policy_versions")
    op.execute("DROP TABLE IF EXISTS ride_data.ingest_audit")
    op.execute("DROP TABLE IF EXISTS ride_data.scenario_tags")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_external_conditions")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_device_signals")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_promo_applications")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_fare_adjustments")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_fare_breakdowns")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_call_attempts")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_chat_messages")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_stops")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_gps_samples")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_waypoints")
    op.execute("DROP TABLE IF EXISTS ride_data.ride_route_plans")
    op.execute("DROP TABLE IF EXISTS ride_data.rides")
    op.execute("DROP TABLE IF EXISTS ride_data.user_dispute_counters")
    op.execute("DROP TABLE IF EXISTS ride_data.user_rating_history")
    op.execute("DROP TABLE IF EXISTS ride_data.user_profiles")
    op.execute("DROP TABLE IF EXISTS ride_data.users")
    op.execute("DROP SCHEMA IF EXISTS case_archive")
    op.execute("DROP SCHEMA IF EXISTS ride_data")
    op.execute("DROP ROLE IF EXISTS ryde_backend_readonly")
