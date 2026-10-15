"""SQLAlchemy 2.0 models for the backend-owned `tribunal` schema (write matrix §6).

The backend OWNS and migrates this schema. These are the tables the backend writes:
`case_*`, `model_work_*`, `ruling_*`, `case_history`, `idempotency_keys`. It never writes
`ride_data` or `case_archive` — its DB role has SELECT-only there, enforced in PostgreSQL.

Phase Zero's request path uses the in-process `ResultStore` (offline, CI). These models +
the Alembic migration define the durable schema the store maps onto at integration; the ORM
persistence adapter is a later integration task behind the same `ResultStore` surface.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "tribunal"


class Base(DeclarativeBase):
    metadata_schema = SCHEMA


class CaseRow(Base):
    __tablename__ = "case_records"
    __table_args__ = {"schema": SCHEMA}

    case_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    ride_id: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32))
    filed_by: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    claimed_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="SGD")
    category_details: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_files: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    filed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    evidence_bundle: Mapped[list] = mapped_column(JSON, default=list)
    case_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewer_approved_ruling: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ModelWorkRow(Base):
    __tablename__ = "model_work"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.case_records.case_id"), index=True
    )
    policy_version: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict] = mapped_column(JSON)  # advocates + judge block, durable (D-05)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RulingRow(Base):
    __tablename__ = "rulings"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.case_records.case_id"), index=True
    )
    ruling_type: Mapped[str] = mapped_column(String(24))
    recommended_action: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text)
    evidence_references: Mapped[list] = mapped_column(JSON, default=list)
    policy_references: Mapped[list] = mapped_column(JSON, default=list)
    precedent_references: Mapped[list] = mapped_column(JSON, default=list)
    escalated: Mapped[bool] = mapped_column(default=False)
    escalation: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    author_type: Mapped[str] = mapped_column(String(24), default="model")
    author_id: Mapped[str] = mapped_column(String(64), default="")
    policy_version: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseHistoryRow(Base):
    __tablename__ = "case_history"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.case_records.case_id"), index=True
    )
    event: Mapped[str] = mapped_column(String(32))  # filed|adjudicated|approved|overridden
    actor_type: Mapped[str] = mapped_column(String(16))  # reviewer | agent
    actor_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # Append-only: an override NEVER updates/deletes an earlier row (contract §2).


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_idempotency_key"),
        {"schema": SCHEMA},
    )

    # The UNIQUE constraint is the concurrency guarantee (contract §2): two simultaneous
    # adjudications with the same key collide on INSERT, so exactly one ruling is produced —
    # not a read-then-write check.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    case_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
