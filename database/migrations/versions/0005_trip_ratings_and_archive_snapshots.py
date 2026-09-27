"""Add trip-linked ratings and self-contained archived trip/case history.

Revision ID: 0005_archive_history
Revises: 0004_company_import_shape
"""
from __future__ import annotations

from alembic import op

revision = "0005_archive_history"
down_revision = "0004_company_import_shape"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ride_data.ride_ratings (
          rating_id bigserial PRIMARY KEY,
          ride_id text NOT NULL REFERENCES ride_data.rides(ride_id) ON DELETE RESTRICT,
          rated_user_id text NOT NULL REFERENCES ride_data.users(user_id) ON DELETE RESTRICT,
          rating_from_role text NOT NULL CHECK (rating_from_role IN ('rider','driver')),
          rating numeric(3,2) NOT NULL CHECK (rating >= 1 AND rating <= 5),
          rated_at timestamptz NOT NULL,
          synthetic boolean NOT NULL DEFAULT true,
          UNIQUE (ride_id, rated_user_id)
        );
        CREATE INDEX ride_ratings_user_time_idx ON ride_data.ride_ratings (rated_user_id, rated_at);

        CREATE TABLE case_archive.archive_user_snapshots (
          archive_user_id text PRIMARY KEY CHECK (archive_user_id ~ '^USR-ARCH-[RD]-[0-9]{6}$'),
          bundle_user_key text UNIQUE,
          role text NOT NULL CHECK (role IN ('rider','driver')),
          display_name text NOT NULL,
          account_age_days integer NOT NULL CHECK (account_age_days >= 0),
          average_rating numeric(3,2) CHECK (average_rating IS NULL OR average_rating BETWEEN 1 AND 5),
          total_trips integer CHECK (total_trips IS NULL OR total_trips >= 0),
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE)
        );
        CREATE TABLE case_archive.archive_trip_snapshots (
          archive_ride_id text PRIMARY KEY CHECK (archive_ride_id ~ '^RIDE-ARCH-[0-9]{6}$'),
          bundle_trip_key text UNIQUE,
          rider_archive_user_id text NOT NULL REFERENCES case_archive.archive_user_snapshots(archive_user_id) ON DELETE RESTRICT,
          driver_archive_user_id text NOT NULL REFERENCES case_archive.archive_user_snapshots(archive_user_id) ON DELETE RESTRICT,
          trip_status text NOT NULL CHECK (trip_status IN ('completed','cancelled_after_arrival','cancelled_before_assignment')),
          trip_at timestamptz NOT NULL,
          requested_at timestamptz NOT NULL,
          accepted_at timestamptz,
          pickup_at timestamptz,
          dropoff_at timestamptz,
          service_tier text NOT NULL DEFAULT 'standard' CHECK (service_tier IN ('standard','premium','assist')),
          quoted_distance_meters integer CHECK (quoted_distance_meters IS NULL OR quoted_distance_meters > 0),
          quoted_duration_seconds integer CHECK (quoted_duration_seconds IS NULL OR quoted_duration_seconds > 0),
          quoted_fare_cents integer CHECK (quoted_fare_cents IS NULL OR quoted_fare_cents >= 0),
          fare_cents integer CHECK (fare_cents IS NULL OR fare_cents >= 0),
          currency char(3) NOT NULL DEFAULT 'SGD',
          rider_rating numeric(3,2) CHECK (rider_rating IS NULL OR rider_rating BETWEEN 1 AND 5),
          driver_rating numeric(3,2) CHECK (driver_rating IS NULL OR driver_rating BETWEEN 1 AND 5),
          fare_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb,
          pricing_structure jsonb NOT NULL DEFAULT '{}'::jsonb,
          pickup_details jsonb NOT NULL DEFAULT '{}'::jsonb,
          dropoff_details jsonb NOT NULL DEFAULT '{}'::jsonb,
          gps_data jsonb NOT NULL DEFAULT '[]'::jsonb,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          CHECK (rider_archive_user_id <> driver_archive_user_id),
          CHECK ((trip_status = 'completed' AND rider_rating IS NOT NULL AND driver_rating IS NOT NULL) OR
                 (trip_status <> 'completed' AND rider_rating IS NULL AND driver_rating IS NULL))
        );

        CREATE SEQUENCE case_archive.archive_user_id_seq START WITH 100001;
        CREATE SEQUENCE case_archive.archive_ride_id_seq START WITH 100001;
        CREATE SEQUENCE case_archive.archive_case_id_seq START WITH 100001;
        CREATE SEQUENCE case_archive.archive_evidence_id_seq START WITH 100001;

        INSERT INTO case_archive.archive_user_snapshots
          (archive_user_id, bundle_user_key, role, display_name, account_age_days, average_rating, total_trips)
        SELECT 'USR-ARCH-R-' || lpad(row_number() OVER (ORDER BY archive_case_id)::text, 6, '0'),
               'migration-rider-' || archive_case_id, 'rider', 'Archived rider ' || archive_case_id,
               365, 4.50, 12
        FROM case_archive.archive_cases;
        INSERT INTO case_archive.archive_user_snapshots
          (archive_user_id, bundle_user_key, role, display_name, account_age_days, average_rating, total_trips)
        SELECT 'USR-ARCH-D-' || lpad(row_number() OVER (ORDER BY archive_case_id)::text, 6, '0'),
               'migration-driver-' || archive_case_id, 'driver', 'Archived driver ' || archive_case_id,
               540, 4.70, 240
        FROM case_archive.archive_cases;
        INSERT INTO case_archive.archive_trip_snapshots
          (archive_ride_id, bundle_trip_key, rider_archive_user_id, driver_archive_user_id, trip_status,
           trip_at, requested_at, accepted_at, pickup_at, dropoff_at, service_tier, quoted_distance_meters,
           quoted_duration_seconds, quoted_fare_cents, fare_cents, currency, rider_rating, driver_rating,
           fare_breakdown, pricing_structure, pickup_details, dropoff_details, gps_data)
        SELECT c.archive_ride_id, 'migration-trip-' || c.archive_case_id,
          (SELECT u.archive_user_id FROM case_archive.archive_user_snapshots u
           WHERE u.bundle_user_key = 'migration-rider-' || c.archive_case_id),
          (SELECT u.archive_user_id FROM case_archive.archive_user_snapshots u
           WHERE u.bundle_user_key = 'migration-driver-' || c.archive_case_id),
          'completed', c.created_at - interval '1 day', c.created_at - interval '1 day',
          c.created_at - interval '1 day' + interval '2 minutes',
          c.created_at - interval '1 day' + interval '7 minutes',
          c.created_at - interval '1 day' + interval '27 minutes', 'standard', 7000, 1200,
          cl.monetary_impact_cents, cl.monetary_impact_cents, 'SGD', 4.70, 4.50,
          '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb
        FROM case_archive.archive_cases c
        LEFT JOIN case_archive.archive_case_classifications cl USING (archive_case_id);
        ALTER TABLE case_archive.archive_case_evidence ADD COLUMN bundle_evidence_key text UNIQUE;
        UPDATE case_archive.archive_case_evidence
        SET bundle_evidence_key = 'migration:' || archive_evidence_id;
        ALTER TABLE case_archive.archive_cases
          DROP CONSTRAINT archive_cases_archive_ride_id_key,
          ADD CONSTRAINT archive_cases_archive_ride_id_fkey
            FOREIGN KEY (archive_ride_id) REFERENCES case_archive.archive_trip_snapshots(archive_ride_id)
            ON DELETE RESTRICT,
          ADD COLUMN filing_archive_user_id text REFERENCES case_archive.archive_user_snapshots(archive_user_id)
            ON DELETE RESTRICT,
          ADD COLUMN bundle_case_key text UNIQUE;
        WITH numbered AS (
          SELECT archive_case_id, row_number() OVER (ORDER BY archive_case_id) AS n
          FROM case_archive.archive_cases
        )
        UPDATE case_archive.archive_cases c
        SET filing_archive_user_id = CASE WHEN c.filed_by = 'rider'
          THEN 'USR-ARCH-R-' || lpad(numbered.n::text, 6, '0')
          ELSE 'USR-ARCH-D-' || lpad(numbered.n::text, 6, '0') END
        FROM numbered WHERE numbered.archive_case_id = c.archive_case_id;
        ALTER TABLE case_archive.archive_cases ALTER COLUMN filing_archive_user_id SET NOT NULL;
        ALTER TABLE case_archive.archive_cases DROP CONSTRAINT archive_cases_category_check;
        ALTER TABLE case_archive.archive_cases ADD CONSTRAINT archive_cases_category_check CHECK
          (category IN ('route_deviation','no_show_charge','fare_calculation','other_cancellation_fee',
                        'property_damage','safety_incident','lost_item','conduct_complaint'));

        CREATE TABLE case_archive.archive_case_rulings (
          ruling_id bigserial PRIMARY KEY,
          archive_case_id text NOT NULL REFERENCES case_archive.archive_cases(archive_case_id) ON DELETE RESTRICT,
          ruling_stage text NOT NULL CHECK (ruling_stage IN ('model_proposed','reviewer_approved')),
          decision_origin text NOT NULL CHECK (decision_origin IN ('agent','human')),
          verdict text NOT NULL CHECK (verdict IN ('refund','compensation','no_action','escalated')),
          ruling_type text NOT NULL CHECK (ruling_type IN ('refund','compensation','no_action')),
          action_description text NOT NULL,
          amount_cents integer NOT NULL CHECK (amount_cents >= 0),
          currency char(3) NOT NULL DEFAULT 'SGD',
          confidence numeric(4,3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
          decided_at timestamptz NOT NULL,
          synthetic boolean NOT NULL DEFAULT true CHECK (synthetic IS TRUE),
          UNIQUE (archive_case_id, ruling_stage),
          CHECK ((ruling_stage = 'model_proposed' AND decision_origin = 'agent') OR
                 (ruling_stage = 'reviewer_approved' AND decision_origin = 'human'))
        );
        INSERT INTO case_archive.archive_case_rulings
          (archive_case_id, ruling_stage, decision_origin, verdict, ruling_type, action_description,
           amount_cents, currency, confidence, decided_at, synthetic)
        SELECT d.archive_case_id,
          CASE WHEN h.human_reviewed THEN 'reviewer_approved' ELSE 'model_proposed' END,
          d.decision_origin, d.verdict, d.ruling_type, d.recommended_action_description,
          d.recommended_amount_cents, d.currency, d.confidence, d.decided_at, d.synthetic
        FROM case_archive.archive_case_decisions d
        LEFT JOIN case_archive.archive_human_reviews h USING (archive_case_id);
        GRANT SELECT ON case_archive.archive_user_snapshots, case_archive.archive_trip_snapshots,
          case_archive.archive_case_rulings TO ryde_backend_readonly;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE case_archive.archive_case_rulings;
        ALTER TABLE case_archive.archive_cases DROP CONSTRAINT archive_cases_archive_ride_id_fkey;
        ALTER TABLE case_archive.archive_cases DROP CONSTRAINT archive_cases_category_check;
        ALTER TABLE case_archive.archive_cases DROP COLUMN bundle_case_key;
        ALTER TABLE case_archive.archive_cases DROP COLUMN filing_archive_user_id;
        ALTER TABLE case_archive.archive_cases ADD CONSTRAINT archive_cases_category_check CHECK
          (category IN ('route_deviation','no_show_charge','property_damage','safety_incident'));
        ALTER TABLE case_archive.archive_cases ADD CONSTRAINT archive_cases_archive_ride_id_key UNIQUE (archive_ride_id);
        DROP SEQUENCE case_archive.archive_case_id_seq;
        ALTER TABLE case_archive.archive_case_evidence DROP COLUMN bundle_evidence_key;
        DROP SEQUENCE case_archive.archive_evidence_id_seq;
        DROP SEQUENCE case_archive.archive_ride_id_seq;
        DROP SEQUENCE case_archive.archive_user_id_seq;
        DROP TABLE case_archive.archive_trip_snapshots;
        DROP TABLE case_archive.archive_user_snapshots;
        DROP INDEX ride_data.ride_ratings_user_time_idx;
        DROP TABLE ride_data.ride_ratings;
        """
    )
