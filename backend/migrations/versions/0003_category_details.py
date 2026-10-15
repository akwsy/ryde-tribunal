"""Persist structured category intake without changing historical case records.

Revision ID: 0003_category_details
Revises: 0002_case_result_origin
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_category_details"
down_revision = "0002_case_result_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_records", sa.Column(
        "category_details", sa.JSON(), nullable=False, server_default="{}"), schema="tribunal")
    op.add_column("case_records", sa.Column(
        "attachment_files", sa.JSON(), nullable=False, server_default="{}"), schema="tribunal")


def downgrade() -> None:
    op.drop_column("case_records", "category_details", schema="tribunal")
    op.drop_column("case_records", "attachment_files", schema="tribunal")
