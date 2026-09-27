"""Rename canonical no_show category to no_show_charge.

Revision ID: 0002_no_show_charge_category
Revises: 0001_phase0_schema
Create Date: 2026-09-24
"""
from __future__ import annotations

from alembic import op

revision = "0002_no_show_charge_category"
down_revision = "0001_phase0_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE case_archive.archive_cases DROP CONSTRAINT archive_cases_category_check")
    op.execute("UPDATE case_archive.archive_cases SET category = 'no_show_charge' WHERE category = 'no_show'")
    op.execute(
        "UPDATE case_archive.archive_case_classifications "
        "SET primary_classification = 'no_show_charge' WHERE primary_classification = 'no_show'"
    )
    op.execute(
        """
        UPDATE case_archive.archive_case_classifications AS c
        SET secondary_classifications = (
          SELECT COALESCE(jsonb_agg(
            CASE WHEN item = '"no_show"'::jsonb THEN '"no_show_charge"'::jsonb ELSE item END
          ), '[]'::jsonb)
          FROM jsonb_array_elements(c.secondary_classifications) AS items(item)
        )
        WHERE c.secondary_classifications @> '["no_show"]'::jsonb
        """
    )
    op.execute(
        """
        UPDATE case_archive.archive_precedent_index
        SET category = 'no_show_charge',
            feature_vector = jsonb_set(feature_vector, '{category}', '"no_show_charge"'::jsonb, true)
        WHERE category = 'no_show'
        """
    )
    op.execute(
        "UPDATE ride_data.scenario_tags SET tag = 'category_no_show_charge' "
        "WHERE tag = 'category_no_show'"
    )
    op.execute(
        """
        ALTER TABLE case_archive.archive_cases
        ADD CONSTRAINT archive_cases_category_check
        CHECK (category IN ('route_deviation', 'no_show_charge', 'property_damage', 'safety_incident'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE case_archive.archive_cases DROP CONSTRAINT archive_cases_category_check")
    op.execute("UPDATE ride_data.scenario_tags SET tag = 'category_no_show' WHERE tag = 'category_no_show_charge'")
    op.execute(
        """
        UPDATE case_archive.archive_precedent_index
        SET category = 'no_show',
            feature_vector = jsonb_set(feature_vector, '{category}', '"no_show"'::jsonb, true)
        WHERE category = 'no_show_charge'
        """
    )
    op.execute(
        "UPDATE case_archive.archive_case_classifications "
        "SET primary_classification = 'no_show' WHERE primary_classification = 'no_show_charge'"
    )
    op.execute(
        """
        UPDATE case_archive.archive_case_classifications AS c
        SET secondary_classifications = (
          SELECT COALESCE(jsonb_agg(
            CASE WHEN item = '"no_show_charge"'::jsonb THEN '"no_show"'::jsonb ELSE item END
          ), '[]'::jsonb)
          FROM jsonb_array_elements(c.secondary_classifications) AS items(item)
        )
        WHERE c.secondary_classifications @> '["no_show_charge"]'::jsonb
        """
    )
    op.execute("UPDATE case_archive.archive_cases SET category = 'no_show' WHERE category = 'no_show_charge'")
    op.execute(
        """
        ALTER TABLE case_archive.archive_cases
        ADD CONSTRAINT archive_cases_category_check
        CHECK (category IN ('route_deviation', 'no_show', 'property_damage', 'safety_incident'))
        """
    )
