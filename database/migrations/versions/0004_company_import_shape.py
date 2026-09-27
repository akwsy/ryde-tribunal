"""Add queryable fields needed by company CSV imports.

Revision ID: 0004_company_import_shape
Revises: 0003_allow_mixed_local_data
Create Date: 2026-09-24
"""
from __future__ import annotations

from alembic import op

revision = "0004_company_import_shape"
down_revision = "0003_allow_mixed_local_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ride_data.users
          ALTER COLUMN display_handle DROP NOT NULL,
          ALTER COLUMN created_at DROP NOT NULL,
          ALTER COLUMN account_status DROP NOT NULL,
          ADD COLUMN full_name text;
        ALTER TABLE ride_data.user_profiles
          ALTER COLUMN lifetime_completed_rides DROP NOT NULL,
          ALTER COLUMN average_rating TYPE numeric USING average_rating::numeric,
          ALTER COLUMN rating_trend DROP NOT NULL,
          ADD COLUMN total_trips integer CHECK (total_trips >= 0),
          ADD COLUMN dispute_history_total integer CHECK (dispute_history_total >= 0),
          ADD COLUMN dispute_history_upheld integer CHECK (dispute_history_upheld >= 0),
          ADD COLUMN dispute_history_rejected integer CHECK (dispute_history_rejected >= 0),
          ADD COLUMN dispute_history_upheld_against integer CHECK (dispute_history_upheld_against >= 0),
          ADD COLUMN fraud_flag_count integer CHECK (fraud_flag_count >= 0),
          ADD COLUMN fraud_flag_details text,
          ADD COLUMN payment_method text,
          ADD COLUMN vehicle text;
        ALTER TABLE ride_data.user_profiles
          ADD COLUMN evidence_source text,
          ADD COLUMN verification_status text NOT NULL DEFAULT 'unverified'
            CHECK (verification_status IN ('verified', 'unverified', 'disputed', 'unverifiable')),
          ADD COLUMN verified_by text,
          ADD COLUMN verified_at timestamptz,
          ADD COLUMN provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE ride_data.user_dispute_counters
          ALTER COLUMN disputes_30d DROP NOT NULL,
          ALTER COLUMN disputes_180d DROP NOT NULL,
          ALTER COLUMN route_deviation_count DROP NOT NULL,
          ALTER COLUMN no_show_count DROP NOT NULL,
          ALTER COLUMN property_damage_count DROP NOT NULL,
          ALTER COLUMN safety_incident_count DROP NOT NULL;
        ALTER TABLE ride_data.rides
          ALTER COLUMN requested_at DROP NOT NULL,
          ALTER COLUMN ride_status DROP NOT NULL,
          ALTER COLUMN service_tier DROP NOT NULL,
          ALTER COLUMN quoted_distance_meters DROP NOT NULL,
          ALTER COLUMN quoted_duration_seconds DROP NOT NULL,
          ALTER COLUMN quoted_fare_cents DROP NOT NULL,
          ADD COLUMN scheduled_at timestamptz,
          ADD COLUMN cancellation_at timestamptz,
          ADD COLUMN cancellation_reason text,
          ADD COLUMN evidence_source text,
          ADD COLUMN verification_status text NOT NULL DEFAULT 'unverified'
            CHECK (verification_status IN ('verified', 'unverified', 'disputed', 'unverifiable')),
          ADD COLUMN verified_by text,
          ADD COLUMN verified_at timestamptz,
          ADD COLUMN provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE ride_data.ride_route_plans
          ALTER COLUMN pickup_lat TYPE numeric USING pickup_lat::numeric,
          ALTER COLUMN pickup_lon TYPE numeric USING pickup_lon::numeric,
          ALTER COLUMN dropoff_lat TYPE numeric USING dropoff_lat::numeric,
          ALTER COLUMN dropoff_lon TYPE numeric USING dropoff_lon::numeric,
          ALTER COLUMN planned_distance_meters DROP NOT NULL,
          ALTER COLUMN actual_distance_meters DROP NOT NULL,
          ALTER COLUMN planned_duration_seconds DROP NOT NULL,
          ALTER COLUMN actual_duration_seconds DROP NOT NULL,
          ADD COLUMN driver_arrival_at timestamptz,
          ADD COLUMN driver_wait_start_at timestamptz,
          ADD COLUMN evidence_source text,
          ADD COLUMN verification_status text NOT NULL DEFAULT 'unverified'
            CHECK (verification_status IN ('verified', 'unverified', 'disputed', 'unverifiable')),
          ADD COLUMN verified_by text,
          ADD COLUMN verified_at timestamptz,
          ADD COLUMN provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE ride_data.ride_gps_samples
          ALTER COLUMN lat TYPE numeric USING lat::numeric,
          ALTER COLUMN lon TYPE numeric USING lon::numeric,
          ALTER COLUMN speed_meters_per_second TYPE numeric USING speed_meters_per_second::numeric,
          ALTER COLUMN accuracy_meters DROP NOT NULL,
          ALTER COLUMN speed_meters_per_second DROP NOT NULL,
          ALTER COLUMN collector DROP NOT NULL,
          ADD COLUMN sequence_no integer CHECK (sequence_no >= 0),
          ADD COLUMN speed_kmh numeric CHECK (speed_kmh >= 0),
          ADD COLUMN status text,
          ADD COLUMN source_system text,
          ADD COLUMN evidence_source text,
          ADD COLUMN verification_status text NOT NULL DEFAULT 'unverified'
            CHECK (verification_status IN ('verified', 'unverified', 'disputed', 'unverifiable')),
          ADD COLUMN verified_by text,
          ADD COLUMN verified_at timestamptz,
          ADD COLUMN provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE ride_data.ride_chat_messages
          DROP CONSTRAINT ride_chat_messages_participant_role_check,
          ADD CONSTRAINT ride_chat_messages_participant_role_check
            CHECK (participant_role IN ('rider', 'driver', 'support', 'system')),
          ADD COLUMN sequence_no integer CHECK (sequence_no >= 0),
          ADD COLUMN message_type text NOT NULL DEFAULT 'message',
          ADD COLUMN source_system text,
          ADD COLUMN evidence_source text,
          ADD COLUMN verification_status text NOT NULL DEFAULT 'unverified'
            CHECK (verification_status IN ('verified', 'unverified', 'disputed', 'unverifiable')),
          ADD COLUMN verified_by text,
          ADD COLUMN verified_at timestamptz,
          ADD COLUMN provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE ride_data.ride_fare_breakdowns
          ALTER COLUMN base_fare_cents DROP NOT NULL,
          ALTER COLUMN distance_fare_cents DROP NOT NULL,
          ALTER COLUMN time_fare_cents DROP NOT NULL,
          ALTER COLUMN waiting_fare_cents DROP NOT NULL,
          ALTER COLUMN surge_multiplier DROP NOT NULL,
          ALTER COLUMN surge_fare_cents DROP NOT NULL,
          ALTER COLUMN cancellation_fee_cents DROP NOT NULL,
          ALTER COLUMN platform_fee_cents DROP NOT NULL,
          ALTER COLUMN total_fare_cents DROP NOT NULL,
          ADD COLUMN evidence_source text,
          ADD COLUMN verification_status text NOT NULL DEFAULT 'unverified'
            CHECK (verification_status IN ('verified', 'unverified', 'disputed', 'unverifiable')),
          ADD COLUMN verified_by text,
          ADD COLUMN verified_at timestamptz,
          ADD COLUMN provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
        CREATE TABLE ride_data.external_user_ids (
          source_system text NOT NULL CHECK (length(trim(source_system)) > 0),
          company_user_id text NOT NULL CHECK (length(trim(company_user_id)) > 0),
          user_id text NOT NULL REFERENCES ride_data.users(user_id) ON DELETE RESTRICT,
          content_sha256 char(64) NOT NULL,
          PRIMARY KEY (source_system, company_user_id),
          UNIQUE (user_id)
        );
        CREATE TABLE ride_data.external_trip_ids (
          source_system text NOT NULL CHECK (length(trim(source_system)) > 0),
          company_trip_id text NOT NULL CHECK (length(trim(company_trip_id)) > 0),
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          content_sha256 char(64) NOT NULL,
          PRIMARY KEY (source_system, company_trip_id),
          UNIQUE (ride_id)
        );
        CREATE TABLE ride_data.ride_app_events (
          event_id text PRIMARY KEY CHECK (event_id ~ '^EV-[0-9]{6}$'),
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          sequence_no integer NOT NULL CHECK (sequence_no >= 0),
          event_at timestamptz NOT NULL,
          event_type text NOT NULL,
          details text NOT NULL,
          source_system text,
          evidence_source text,
          verification_status text NOT NULL DEFAULT 'unverified'
            CHECK (verification_status IN ('verified', 'unverified', 'disputed', 'unverifiable')),
          verified_by text,
          verified_at timestamptz,
          provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
          synthetic boolean NOT NULL DEFAULT false,
          UNIQUE (ride_id, sequence_no)
        );
        CREATE SEQUENCE ride_data.imported_rider_id_seq START WITH 100000;
        CREATE SEQUENCE ride_data.imported_driver_id_seq START WITH 100000;
        CREATE SEQUENCE ride_data.imported_ride_id_seq START WITH 100000;
        CREATE SEQUENCE ride_data.imported_evidence_id_seq START WITH 100000;
        GRANT SELECT ON ride_data.external_user_ids, ride_data.external_trip_ids,
          ride_data.ride_app_events TO ryde_backend_readonly;
        UPDATE ride_data.ride_gps_samples
          SET verification_status = 'verified' WHERE synthetic IS TRUE;
        UPDATE ride_data.ride_chat_messages
          SET verification_status = 'verified' WHERE synthetic IS TRUE;
        UPDATE ride_data.user_profiles
          SET verification_status = 'verified', evidence_source = 'system_record' WHERE synthetic IS TRUE;
        UPDATE ride_data.rides
          SET verification_status = 'verified', evidence_source = 'system_record' WHERE synthetic IS TRUE;
        UPDATE ride_data.ride_route_plans
          SET verification_status = 'verified', evidence_source = 'system_record' WHERE synthetic IS TRUE;
        UPDATE ride_data.ride_fare_breakdowns
          SET verification_status = 'verified', evidence_source = 'system_record' WHERE synthetic IS TRUE;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM ride_data.ride_app_events)
             OR EXISTS (SELECT 1 FROM ride_data.external_trip_ids)
             OR EXISTS (SELECT 1 FROM ride_data.external_user_ids)
             OR EXISTS (SELECT 1 FROM ride_data.rides WHERE synthetic IS FALSE)
             OR EXISTS (SELECT 1 FROM ride_data.users WHERE synthetic IS FALSE) THEN
            RAISE EXCEPTION 'cannot downgrade while company-imported records exist';
          END IF;
        END
        $$;
        DROP TABLE ride_data.ride_app_events;
        DROP TABLE ride_data.external_trip_ids;
        DROP TABLE ride_data.external_user_ids;
        DROP SEQUENCE ride_data.imported_rider_id_seq;
        DROP SEQUENCE ride_data.imported_driver_id_seq;
        DROP SEQUENCE ride_data.imported_ride_id_seq;
        DROP SEQUENCE ride_data.imported_evidence_id_seq;
        ALTER TABLE ride_data.ride_fare_breakdowns
          DROP COLUMN provenance,
          DROP COLUMN verified_at,
          DROP COLUMN verified_by,
          DROP COLUMN verification_status,
          DROP COLUMN evidence_source,
          ALTER COLUMN base_fare_cents SET NOT NULL,
          ALTER COLUMN distance_fare_cents SET NOT NULL,
          ALTER COLUMN time_fare_cents SET NOT NULL,
          ALTER COLUMN waiting_fare_cents SET NOT NULL,
          ALTER COLUMN surge_multiplier SET NOT NULL,
          ALTER COLUMN surge_fare_cents SET NOT NULL,
          ALTER COLUMN cancellation_fee_cents SET NOT NULL,
          ALTER COLUMN platform_fee_cents SET NOT NULL,
          ALTER COLUMN total_fare_cents SET NOT NULL;
        ALTER TABLE ride_data.ride_chat_messages
          DROP COLUMN verified_at,
          DROP COLUMN verified_by,
          DROP COLUMN provenance,
          DROP COLUMN evidence_source,
          DROP COLUMN verification_status,
          DROP COLUMN source_system,
          DROP COLUMN message_type,
          DROP COLUMN sequence_no,
          DROP CONSTRAINT ride_chat_messages_participant_role_check,
          ADD CONSTRAINT ride_chat_messages_participant_role_check
            CHECK (participant_role IN ('rider', 'driver', 'support'));
        ALTER TABLE ride_data.ride_gps_samples
          DROP COLUMN verified_at,
          DROP COLUMN verified_by,
          DROP COLUMN provenance,
          DROP COLUMN evidence_source,
          DROP COLUMN verification_status,
          DROP COLUMN source_system,
          DROP COLUMN status,
          DROP COLUMN speed_kmh,
          DROP COLUMN sequence_no,
          ALTER COLUMN lat TYPE numeric(9,6) USING lat::numeric(9,6),
          ALTER COLUMN lon TYPE numeric(9,6) USING lon::numeric(9,6),
          ALTER COLUMN speed_meters_per_second TYPE numeric(6,2) USING speed_meters_per_second::numeric(6,2),
          ALTER COLUMN accuracy_meters SET NOT NULL,
          ALTER COLUMN speed_meters_per_second SET NOT NULL,
          ALTER COLUMN collector SET NOT NULL;
        ALTER TABLE ride_data.ride_route_plans
          DROP COLUMN provenance,
          DROP COLUMN verified_at,
          DROP COLUMN verified_by,
          DROP COLUMN verification_status,
          DROP COLUMN evidence_source,
          DROP COLUMN driver_wait_start_at,
          DROP COLUMN driver_arrival_at,
          ALTER COLUMN pickup_lat TYPE numeric(9,6) USING pickup_lat::numeric(9,6),
          ALTER COLUMN pickup_lon TYPE numeric(9,6) USING pickup_lon::numeric(9,6),
          ALTER COLUMN dropoff_lat TYPE numeric(9,6) USING dropoff_lat::numeric(9,6),
          ALTER COLUMN dropoff_lon TYPE numeric(9,6) USING dropoff_lon::numeric(9,6),
          ALTER COLUMN planned_distance_meters SET NOT NULL,
          ALTER COLUMN actual_distance_meters SET NOT NULL,
          ALTER COLUMN planned_duration_seconds SET NOT NULL,
          ALTER COLUMN actual_duration_seconds SET NOT NULL;
        ALTER TABLE ride_data.rides
          DROP COLUMN provenance,
          DROP COLUMN verified_at,
          DROP COLUMN verified_by,
          DROP COLUMN verification_status,
          DROP COLUMN evidence_source,
          DROP COLUMN cancellation_reason,
          DROP COLUMN cancellation_at,
          DROP COLUMN scheduled_at,
          ALTER COLUMN service_tier SET NOT NULL,
          ALTER COLUMN ride_status SET NOT NULL,
          ALTER COLUMN requested_at SET NOT NULL,
          ALTER COLUMN quoted_distance_meters SET NOT NULL,
          ALTER COLUMN quoted_duration_seconds SET NOT NULL,
          ALTER COLUMN quoted_fare_cents SET NOT NULL;
        ALTER TABLE ride_data.user_dispute_counters
          ALTER COLUMN disputes_30d SET NOT NULL,
          ALTER COLUMN disputes_180d SET NOT NULL,
          ALTER COLUMN route_deviation_count SET NOT NULL,
          ALTER COLUMN no_show_count SET NOT NULL,
          ALTER COLUMN property_damage_count SET NOT NULL,
          ALTER COLUMN safety_incident_count SET NOT NULL;
        ALTER TABLE ride_data.user_profiles
          DROP COLUMN provenance,
          DROP COLUMN verified_at,
          DROP COLUMN verified_by,
          DROP COLUMN verification_status,
          DROP COLUMN evidence_source,
          DROP COLUMN vehicle,
          DROP COLUMN payment_method,
          DROP COLUMN fraud_flag_details,
          DROP COLUMN fraud_flag_count,
          DROP COLUMN total_trips,
          DROP COLUMN dispute_history_upheld_against,
          DROP COLUMN dispute_history_rejected,
          DROP COLUMN dispute_history_upheld,
          DROP COLUMN dispute_history_total,
          ALTER COLUMN average_rating TYPE numeric(3,2) USING average_rating::numeric(3,2),
          ALTER COLUMN lifetime_completed_rides SET NOT NULL,
          ALTER COLUMN rating_trend SET NOT NULL;
        ALTER TABLE ride_data.users
          DROP COLUMN full_name,
          ALTER COLUMN display_handle SET NOT NULL,
          ALTER COLUMN account_status SET NOT NULL,
          ALTER COLUMN created_at SET NOT NULL;
        """
    )
