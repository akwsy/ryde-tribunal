-- Run as a PostgreSQL administrator while connected to the target Ryde Tribunal database.
-- Set the role password interactively with `psql`'s `\password ryde_data_importer` command.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ryde_data_importer') THEN
    CREATE ROLE ryde_data_importer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  ELSE
    ALTER ROLE ryde_data_importer WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END
$$;

GRANT CONNECT ON DATABASE ryde_tribunal TO ryde_data_importer;
REVOKE ALL ON SCHEMA ride_data FROM ryde_data_importer;
GRANT USAGE ON SCHEMA ride_data TO ryde_data_importer;

REVOKE ALL ON ALL TABLES IN SCHEMA ride_data FROM ryde_data_importer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA ride_data FROM ryde_data_importer;

-- The import path appends rows only. SELECT is limited to the company-ID maps used for
-- duplicate detection and the users table used to verify an existing user's role.
GRANT SELECT ON ride_data.external_user_ids, ride_data.external_trip_ids
  TO ryde_data_importer;
GRANT SELECT (user_id, role) ON ride_data.users TO ryde_data_importer;

GRANT INSERT ON ride_data.users, ride_data.user_profiles, ride_data.user_dispute_counters,
  ride_data.external_user_ids, ride_data.rides, ride_data.external_trip_ids,
  ride_data.ride_route_plans, ride_data.ride_fare_breakdowns, ride_data.ride_ratings, ride_data.ride_gps_samples,
  ride_data.ride_chat_messages, ride_data.ride_app_events TO ryde_data_importer;

GRANT USAGE ON SEQUENCE ride_data.imported_rider_id_seq,
  ride_data.imported_driver_id_seq, ride_data.imported_ride_id_seq,
  ride_data.imported_evidence_id_seq, ride_data.ride_ratings_rating_id_seq TO ryde_data_importer;

-- Keep the legacy backend role strictly read-only.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA ride_data
  FROM ryde_backend_readonly;
REVOKE USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA ride_data
  FROM ryde_backend_readonly;
