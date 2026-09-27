"""enforce ordinary identifiers for historical snapshots

Revision ID: 0008_canonical_record_ids
Revises: 0007_global_archive_entity_ids

Run the one-time cross-schema ID remap after 0007 and before upgrading to this revision.
"""
from __future__ import annotations

from alembic import op

revision = "0008_canonical_record_ids"
down_revision = "0007_global_archive_entity_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    constraints = (
        ("archive_cases", "archive_cases_archive_case_id_check",
         "archive_case_id ~ '^DSP-[0-9]{6}$'"),
        ("archive_cases", "archive_cases_archive_ride_id_check",
         "archive_ride_id ~ '^RIDE-[0-9]{6}$'"),
        ("archive_trip_snapshots", "archive_trip_snapshots_archive_ride_id_check",
         "archive_ride_id ~ '^RIDE-[0-9]{6}$'"),
        ("archive_user_snapshots", "archive_user_snapshots_archive_user_id_check",
         "archive_user_id ~ '^USR-[RD]-[0-9]{6}$'"),
        ("archive_case_evidence", "archive_case_evidence_identifier_check",
         "archive_evidence_id ~ '^EV-[0-9]{6}$'"),
        ("archive_policy_versions", "archive_policy_versions_surrogate_id_check",
         "policy_version_id ~ '^POLICY-[0-9]{6}$'"),
    )
    for table, name, predicate in constraints:
        op.execute(f"ALTER TABLE case_archive.{table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE case_archive.{table} ADD CONSTRAINT {name} CHECK ({predicate})")


def downgrade() -> None:
    transitional = (
        ("archive_cases", "archive_cases_archive_case_id_check",
         "archive_case_id ~ '^DSP-(ARCH-)?[0-9]{6}$'"),
        ("archive_trip_snapshots", "archive_trip_snapshots_archive_ride_id_check",
         "archive_ride_id ~ '^(RIDE-ARCH-|RIDE-)[0-9]{6}$'"),
        ("archive_user_snapshots", "archive_user_snapshots_archive_user_id_check",
         "archive_user_id ~ '^(USR-ARCH-[RD]-|USR-[RD]-)[0-9]{6}$'"),
        ("archive_case_evidence", "archive_case_evidence_identifier_check",
         "archive_evidence_id ~ '^(ARCH-EV-[0-9]{6}-[0-9]{2}|EV-[0-9]{6})$'"),
        ("archive_policy_versions", "archive_policy_versions_surrogate_id_check",
         "policy_version_id ~ '^(ARCH-POLICY-|POLICY-)[0-9]{6}$'"),
    )
    for table, name, predicate in transitional:
        op.execute(f"ALTER TABLE case_archive.{table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE case_archive.{table} ADD CONSTRAINT {name} CHECK ({predicate})")
