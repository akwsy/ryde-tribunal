"""transition archive snapshot IDs to shared per-entity identifier formats

Revision ID: 0007_global_archive_entity_ids
Revises: 0006_global_case_id_transition

The lead-owned one-time remap rewrites existing IDs and dependent references. During the
transition both the historical ARCH form and the ordinary form are accepted. New rows use
ordinary IDs allocated from the same per-entity sequences as live/imported records.
"""
from __future__ import annotations

from alembic import op

revision = "0007_global_archive_entity_ids"
down_revision = "0006_global_case_id_transition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The lead-owned remap updates archive primary keys in place. Let PostgreSQL
    # carry those changes through archive foreign keys atomically, rather than
    # requiring the remapper to temporarily disable referential integrity.
    op.execute(
        """
        DO $$
        DECLARE
          fk record;
          definition text;
        BEGIN
          FOR fk IN
            SELECT c.conrelid::regclass AS table_name,
                   c.conname,
                   pg_get_constraintdef(c.oid) AS definition
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE c.contype = 'f' AND n.nspname = 'case_archive'
          LOOP
            definition := replace(fk.definition, ' ON DELETE ', ' ON UPDATE CASCADE ON DELETE ');
            IF definition = fk.definition THEN
              definition := fk.definition || ' ON UPDATE CASCADE';
            END IF;
            EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', fk.table_name, fk.conname);
            EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s',
                           fk.table_name, fk.conname, definition);
          END LOOP;
        END
        $$;
        """
    )
    op.execute(
        "ALTER TABLE case_archive.archive_user_snapshots "
        "DROP CONSTRAINT archive_user_snapshots_archive_user_id_check"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_user_snapshots "
        "ADD CONSTRAINT archive_user_snapshots_archive_user_id_check "
        "CHECK (archive_user_id ~ '^(USR-ARCH-[RD]-|USR-[RD]-)[0-9]{6}$')"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_trip_snapshots "
        "DROP CONSTRAINT archive_trip_snapshots_archive_ride_id_check"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_trip_snapshots "
        "ADD CONSTRAINT archive_trip_snapshots_archive_ride_id_check "
        "CHECK (archive_ride_id ~ '^(RIDE-ARCH-|RIDE-)[0-9]{6}$')"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_case_evidence "
        "ADD CONSTRAINT archive_case_evidence_identifier_check "
        "CHECK (archive_evidence_id ~ '^(ARCH-EV-[0-9]{6}-[0-9]{2}|EV-[0-9]{6})$')"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_policy_versions "
        "ADD CONSTRAINT archive_policy_versions_surrogate_id_check "
        "CHECK (policy_version_id ~ '^(ARCH-POLICY-|POLICY-)[0-9]{6}$')"
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ryde_backend_writer') THEN
            CREATE ROLE ryde_backend_writer NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE;
          END IF;
        END
        $$;
        GRANT USAGE ON SCHEMA ride_data TO ryde_backend_writer;
        GRANT USAGE ON SEQUENCE ride_data.imported_evidence_id_seq TO ryde_backend_writer;
        """
    )

    # Archive records now draw from the live per-entity sequences in ride_data. Remove the
    # independent allocators so future code cannot accidentally recreate colliding IDs.
    op.execute("DROP SEQUENCE case_archive.archive_user_id_seq")
    op.execute("DROP SEQUENCE case_archive.archive_ride_id_seq")
    op.execute("DROP SEQUENCE case_archive.archive_case_id_seq")
    op.execute("DROP SEQUENCE case_archive.archive_evidence_id_seq")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
          fk record;
          definition text;
        BEGIN
          FOR fk IN
            SELECT c.conrelid::regclass AS table_name,
                   c.conname,
                   pg_get_constraintdef(c.oid) AS definition
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE c.contype = 'f' AND n.nspname = 'case_archive'
          LOOP
            definition := replace(fk.definition, ' ON UPDATE CASCADE', '');
            EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', fk.table_name, fk.conname);
            EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s',
                           fk.table_name, fk.conname, definition);
          END LOOP;
        END
        $$;
        """
    )
    op.execute("CREATE SEQUENCE case_archive.archive_user_id_seq START WITH 100001")
    op.execute("CREATE SEQUENCE case_archive.archive_ride_id_seq START WITH 100001")
    op.execute("CREATE SEQUENCE case_archive.archive_case_id_seq START WITH 100001")
    op.execute("CREATE SEQUENCE case_archive.archive_evidence_id_seq START WITH 100001")
    op.execute(
        "ALTER TABLE case_archive.archive_policy_versions "
        "DROP CONSTRAINT archive_policy_versions_surrogate_id_check"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_case_evidence "
        "DROP CONSTRAINT archive_case_evidence_identifier_check"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_trip_snapshots "
        "DROP CONSTRAINT archive_trip_snapshots_archive_ride_id_check"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_trip_snapshots "
        "ADD CONSTRAINT archive_trip_snapshots_archive_ride_id_check "
        "CHECK (archive_ride_id ~ '^(RIDE-ARCH-|RIDE-)[0-9]{6}$')"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_user_snapshots "
        "DROP CONSTRAINT archive_user_snapshots_archive_user_id_check"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_user_snapshots "
        "ADD CONSTRAINT archive_user_snapshots_archive_user_id_check "
        "CHECK (archive_user_id ~ '^(USR-ARCH-[RD]-|USR-[RD]-)[0-9]{6}$')"
    )
