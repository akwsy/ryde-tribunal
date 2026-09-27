"""Allow synthetic and imported company rows in the same local ride pool.

Revision ID: 0003_allow_mixed_local_data
Revises: 0002_no_show_charge_category
Create Date: 2026-09-24
"""
from __future__ import annotations

from alembic import op

revision = "0003_allow_mixed_local_data"
down_revision = "0002_no_show_charge_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE constraint_row record;
        BEGIN
          FOR constraint_row IN
            SELECT conrelid::regclass AS table_name, conname
            FROM pg_constraint
            WHERE contype = 'c'
              AND connamespace = 'ride_data'::regnamespace
              AND pg_get_constraintdef(oid) LIKE '%synthetic IS TRUE%'
          LOOP
            EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',
                           constraint_row.table_name, constraint_row.conname);
          END LOOP;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE table_row record;
        has_imported boolean;
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'ride_data' AND column_name = 'synthetic'
          ) THEN
            FOR table_row IN
              SELECT table_name
              FROM information_schema.columns
              WHERE table_schema = 'ride_data' AND column_name = 'synthetic'
            LOOP
              EXECUTE format('SELECT EXISTS (SELECT 1 FROM ride_data.%I WHERE synthetic IS NOT TRUE)',
                             table_row.table_name) INTO has_imported;
              IF has_imported THEN
                RAISE EXCEPTION 'cannot downgrade while company-imported rows exist';
              END IF;
            END LOOP;
          END IF;
        END
        $$;
        """
    )
    # Restore the original protection only after ensuring imported rows are absent.
    op.execute(
        """
        DO $$
        DECLARE table_row record;
        BEGIN
          FOR table_row IN
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema = 'ride_data' AND column_name = 'synthetic'
          LOOP
            EXECUTE format(
              'ALTER TABLE ride_data.%I ADD CONSTRAINT %I CHECK (synthetic IS TRUE)',
              table_row.table_name, table_row.table_name || '_synthetic_check'
            );
          END LOOP;
        END
        $$;
        """
    )
