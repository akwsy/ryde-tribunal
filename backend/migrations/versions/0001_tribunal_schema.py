"""create tribunal schema and backend-owned tables

Revision ID: 0001_tribunal_schema
Revises:
Create Date: 2026-09-22

Creates the backend-owned `tribunal` schema (write matrix §6) and its tables:
case_records, model_work, rulings, case_history, idempotency_keys. The backend owns and
migrates ONLY this schema — never ride_data or case_archive.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_tribunal_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "tribunal"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "case_records",
        sa.Column("case_id", sa.String(32), primary_key=True),
        sa.Column("ride_id", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("filed_by", sa.String(16), nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("claimed_amount_cents", sa.Integer, nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="SGD"),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("filed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_case_records_ride_id", "case_records", ["ride_id"], schema=SCHEMA)

    op.create_table(
        "model_work",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.case_records.case_id"), nullable=False),
        sa.Column("policy_version", sa.String(48), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_model_work_case_id", "model_work", ["case_id"], schema=SCHEMA)

    op.create_table(
        "rulings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.case_records.case_id"), nullable=False),
        sa.Column("ruling_type", sa.String(24), nullable=False),
        sa.Column("recommended_action", sa.JSON, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("reasoning", sa.Text, nullable=False),
        sa.Column("evidence_references", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("policy_references", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("precedent_references", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("escalated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("escalation", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("provider", sa.JSON, nullable=False),
        sa.Column("policy_version", sa.String(48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_rulings_case_id", "rulings", ["case_id"], schema=SCHEMA)

    op.create_table(
        "case_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.case_records.case_id"), nullable=False),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        schema=SCHEMA,
    )
    op.create_index("ix_case_history_case_id", "case_history", ["case_id"], schema=SCHEMA)

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("case_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # UNIQUE is the concurrency guarantee (contract §2): concurrent same-key INSERTs
        # collide, so exactly one ruling is produced.
        sa.UniqueConstraint("idempotency_key", name="uq_idempotency_key"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in ("idempotency_keys", "case_history", "rulings", "model_work", "case_records"):
        op.drop_table(table, schema=SCHEMA)
    # The `tribunal` schema is intentionally NOT dropped here: Alembic's own
    # `tribunal.alembic_version` table still lives in it after a downgrade to base, so a bare
    # DROP SCHEMA would fail. Dropping the schema is an operator action, not a migration step.
