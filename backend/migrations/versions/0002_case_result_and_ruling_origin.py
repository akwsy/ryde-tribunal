"""Persist filed evidence, complete case results and distinct reviewer rulings.

Revision ID: 0002_case_result_origin
Revises: 0001_tribunal_schema
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_case_result_origin"
down_revision: Union[str, None] = "0001_tribunal_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "tribunal"


def upgrade() -> None:
    op.add_column("case_records", sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default="[]"), schema=SCHEMA)
    op.add_column("case_records", sa.Column("evidence_bundle", sa.JSON(), nullable=False, server_default="[]"), schema=SCHEMA)
    op.add_column("case_records", sa.Column("case_result", sa.JSON(), nullable=True), schema=SCHEMA)
    op.add_column("case_records", sa.Column("reviewer_approved_ruling", sa.JSON(), nullable=True), schema=SCHEMA)
    op.add_column("rulings", sa.Column("author_type", sa.String(24), nullable=False, server_default="model"), schema=SCHEMA)
    op.add_column("rulings", sa.Column("author_id", sa.String(64), nullable=False, server_default=""), schema=SCHEMA)
    op.alter_column("rulings", "confidence", existing_type=sa.Float(), nullable=True, schema=SCHEMA)
    op.alter_column("rulings", "provider", existing_type=sa.JSON(), nullable=True, schema=SCHEMA)
    op.alter_column("rulings", "policy_version", existing_type=sa.String(48), nullable=True, schema=SCHEMA)
    op.execute("CREATE SEQUENCE tribunal.case_id_seq START WITH 45")
    op.execute("""
        SELECT setval(
            'tribunal.case_id_seq',
            GREATEST(COALESCE((
                SELECT MAX(substring(case_id FROM 5)::bigint)
                FROM tribunal.case_records
                WHERE case_id ~ '^DSP-[0-9]+$'
            ), 44), 44),
            true
        )
    """)
    op.execute("CREATE SEQUENCE tribunal.evidence_id_seq START WITH 1")
    op.execute("""
        WITH evidence_ids AS (
            SELECT evidence->>'evidence_id' AS evidence_id
            FROM tribunal.case_records AS c
            CROSS JOIN LATERAL json_array_elements(COALESCE(c.evidence_refs, '[]'::json)) AS evidence
            UNION ALL
            SELECT evidence->>'evidence_id' AS evidence_id
            FROM tribunal.case_records AS c
            CROSS JOIN LATERAL json_array_elements(COALESCE(c.evidence_bundle, '[]'::json)) AS evidence
        ), max_id AS (
            SELECT MAX(substring(evidence_id FROM 4)::bigint) AS value
            FROM evidence_ids
            WHERE evidence_id ~ '^EV-[0-9]+$'
        )
        SELECT setval(
            'tribunal.evidence_id_seq',
            GREATEST(COALESCE(value, 1), 1),
            COALESCE(value, 0) > 0
        ) FROM max_id
    """)


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS tribunal.case_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS tribunal.evidence_id_seq")
    op.drop_column("rulings", "author_id", schema=SCHEMA)
    op.drop_column("rulings", "author_type", schema=SCHEMA)
    op.alter_column("rulings", "policy_version", existing_type=sa.String(48), nullable=False, schema=SCHEMA)
    op.alter_column("rulings", "provider", existing_type=sa.JSON(), nullable=False, schema=SCHEMA)
    op.alter_column("rulings", "confidence", existing_type=sa.Float(), nullable=False, schema=SCHEMA)
    op.drop_column("case_records", "reviewer_approved_ruling", schema=SCHEMA)
    op.drop_column("case_records", "case_result", schema=SCHEMA)
    op.drop_column("case_records", "evidence_bundle", schema=SCHEMA)
    op.drop_column("case_records", "evidence_refs", schema=SCHEMA)
