"""Durable backend-owned store for the tribunal schema.

This adapter writes only `tribunal`. The ride/profile/evidence reader remains a separate
read-only connection. Apply backend Alembic migrations before enabling this store.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from app.persistence.models import (
    CaseHistoryRow,
    CaseRow,
    IdempotencyKeyRow,
    ModelWorkRow,
    RulingRow,
)
from app.persistence.reader import CaseRecord, EvidenceRef
from app.persistence.store import Claim, IdempotencyConflict


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _json_evidence(ref: EvidenceRef) -> dict[str, Any]:
    data = ref.model_dump()
    data["class"] = data.pop("class_")
    return data


class PostgresResultStore:
    """Implements the ResultStore API with PostgreSQL persistence and DB-generated IDs."""

    def __init__(self, dsn: str) -> None:
        if dsn.startswith("postgresql://"):
            dsn = dsn.replace("postgresql://", "postgresql+psycopg://", 1)
        self._engine = create_engine(dsn, pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)
        self._idem_guard = threading.Lock()
        self._local_idem: dict[str, dict[str, Any]] = {}

    def allocate_case_id(self) -> str:
        with self._sessions.begin() as session:
            value = session.execute(text("SELECT nextval('tribunal.case_id_seq')")).scalar_one()
        return f"DSP-{value:06d}"

    def allocate_evidence_id(self) -> str:
        with self._sessions.begin() as session:
            # Live tribunal evidence and company-import/archive evidence share the DB-owned
            # sequence. The TRIBUNAL_DATABASE_DSN login must inherit USAGE on this sequence
            # through the ryde_backend_writer group role.
            value = session.execute(
                text("SELECT nextval('ride_data.imported_evidence_id_seq')")
            ).scalar_one()
        return f"EV-{value:06d}"

    def count_filed_cases(self) -> int:
        with self._sessions() as session:
            return session.query(CaseRow).count()

    def save_filed_case(self, case) -> None:
        refs = [_json_evidence(ref) for ref in (case.evidence or [])]
        with self._sessions.begin() as session:
            row = session.get(CaseRow, case.case_id)
            if row is None:
                row = CaseRow(case_id=case.case_id, ride_id=case.ride_id,
                              category=case.category, filed_by=case.filed_by,
                              subject=case.subject, description=case.description,
                              claimed_amount_cents=case.claimed_amount_cents,
                              currency=case.currency, category_details=case.category_details,
                              attachment_files=case.attachment_files,
                              status="queued",
                              filed_at=_timestamp(case.filed_at), evidence_refs=refs)
                session.add(row)
            else:
                row.evidence_refs = refs

    def get_case_status(self, case_id: str) -> str | None:
        with self._sessions() as session:
            row = session.get(CaseRow, case_id)
            return row.status if row else None

    def claim_case_processing(self, case_id: str) -> bool:
        with self._sessions.begin() as session:
            row = session.scalar(select(CaseRow).where(
                CaseRow.case_id == case_id).with_for_update())
            if row is None or row.case_result is not None or row.status != "queued":
                return False
            row.status = "processing"
            return True

    def set_case_status(self, case_id: str, status: str) -> None:
        with self._sessions.begin() as session:
            row = session.get(CaseRow, case_id)
            if row is not None and row.case_result is None:
                row.status = status

    def reset_processing_cases(self) -> int:
        with self._sessions.begin() as session:
            rows = session.scalars(select(CaseRow).where(
                CaseRow.status == "processing", CaseRow.case_result.is_(None)
            )).all()
            for row in rows:
                row.status = "queued"
            return len(rows)

    def get_filed_case(self, case_id: str):
        with self._sessions() as session:
            row = session.get(CaseRow, case_id)
            if row is None:
                return None
            refs = []
            for raw in row.evidence_refs or []:
                data = dict(raw)
                data["class_"] = data.pop("class", data.get("class_", "attachment"))
                refs.append(EvidenceRef.model_validate(data))
            return CaseRecord(case_id=row.case_id, ride_id=row.ride_id,
                              category=row.category, filed_by=row.filed_by,
                              subject=row.subject, description=row.description,
                              claimed_amount_cents=row.claimed_amount_cents,
                              currency=row.currency, filed_at=row.filed_at.isoformat() if row.filed_at else "",
                              category_details=row.category_details or {},
                              attachment_files=row.attachment_files or {}, evidence=refs)

    def save_evidence_bundle(self, case_id: str, evidence: list[dict[str, Any]]) -> None:
        with self._sessions.begin() as session:
            row = session.get(CaseRow, case_id)
            if row is not None:
                row.evidence_bundle = list(evidence)

    def get_evidence_bundle(self, case_id: str) -> list[dict[str, Any]]:
        with self._sessions() as session:
            row = session.get(CaseRow, case_id)
            return list(row.evidence_bundle or []) if row else []

    def find_evidence(self, case_id: str, evidence_id: str):
        return next((e for e in self.get_evidence_bundle(case_id)
                     if e.get("evidence_id") == evidence_id), None)

    def find_party_evidence_global(self, evidence_id: str):
        with self._sessions() as session:
            rows = session.scalars(select(CaseRow)).all()
            for row in rows:
                for raw in row.evidence_refs or []:
                    if raw.get("evidence_id") == evidence_id:
                        data = dict(raw)
                        data["class_"] = data.pop("class", data.get("class_", "attachment"))
                        return row.case_id, EvidenceRef.model_validate(data)
        return None

    def find_party_attachment_global(self, evidence_id: str):
        with self._sessions() as session:
            rows = session.scalars(select(CaseRow)).all()
            for row in rows:
                attachment = (row.attachment_files or {}).get(evidence_id)
                if attachment:
                    return dict(attachment)
        return None

    def find_evidence_global(self, evidence_id: str):
        with self._sessions() as session:
            rows = session.scalars(select(CaseRow)).all()
            for row in rows:
                for item in row.evidence_bundle or []:
                    if item.get("evidence_id") == evidence_id:
                        return dict(item)
        return None

    def save_case_result(self, result: dict[str, Any]) -> None:
        case_id = result["case_id"]
        judge = result.get("judge") or {}
        approved = result.get("reviewer_approved_ruling")
        with self._sessions.begin() as session:
            row = session.get(CaseRow, case_id)
            if row is None:
                raise KeyError(f"case {case_id} is not filed")
            previous_approved = row.reviewer_approved_ruling
            row.status = result["status"]
            row.case_result = result
            row.reviewer_approved_ruling = approved
            if judge and not approved:
                session.add(RulingRow(
                    case_id=case_id,
                    ruling_type=judge["ruling_type"],
                    recommended_action=judge["recommended_action"],
                    confidence=judge["confidence"], reasoning=judge["reasoning"],
                    evidence_references=judge["evidence_references"],
                    policy_references=judge["policy_references"],
                    precedent_references=judge["precedent_references"],
                    escalated=judge["escalation"]["escalated"],
                    escalation=judge["escalation"], provider=judge["provider"],
                    policy_version=result["policy_version"],
                    author_type="model", author_id=judge["provider"]["model"],
                ))
            elif approved and previous_approved != approved:
                session.add(RulingRow(
                    case_id=case_id,
                    ruling_type=approved["ruling_type"],
                    recommended_action=approved.get("recommended_action", {}),
                    confidence=None,
                    reasoning=approved.get("rationale") or "Model-proposed ruling approved by reviewer.",
                    evidence_references=[], policy_references=[], precedent_references=[],
                    escalated=False, escalation={}, provider=None,
                    policy_version=result.get("policy_version"),
                    author_type="human_reviewer", author_id=approved.get("author_id", ""),
                ))

    def get_case_result(self, case_id: str):
        with self._sessions() as session:
            row = session.get(CaseRow, case_id)
            return dict(row.case_result) if row and row.case_result is not None else None

    def list_case_results(self) -> list[dict[str, Any]]:
        with self._sessions() as session:
            return [dict(row.case_result) for row in session.scalars(
                select(CaseRow).order_by(CaseRow.filed_at.asc(), CaseRow.case_id.asc())
            ).all()
                    if row.case_result is not None]

    def list_filed_cases(self) -> list[dict[str, Any]]:
        """Return all tribunal cases, including cases without a CaseResult yet."""
        with self._sessions() as session:
            rows = session.scalars(
                select(CaseRow).order_by(CaseRow.filed_at.asc(), CaseRow.case_id.asc())
            ).all()
            return [
                {
                    "case": CaseRecord(
                        case_id=row.case_id,
                        ride_id=row.ride_id,
                        category=row.category,
                        filed_by=row.filed_by,
                        subject=row.subject,
                        description=row.description,
                        claimed_amount_cents=row.claimed_amount_cents,
                        currency=row.currency,
                        filed_at=row.filed_at.isoformat() if row.filed_at else "",
                        evidence=[],
                    ),
                    "result": dict(row.case_result) if row.case_result is not None else {"status": row.status},
                }
                for row in rows
            ]

    def persist_model_work(self, case_id: str, payload: dict[str, Any]) -> None:
        with self._sessions.begin() as session:
            session.add(ModelWorkRow(case_id=case_id,
                                     policy_version=payload["policy_version"], payload=payload))

    def get_model_work(self, case_id: str) -> list[dict[str, Any]]:
        with self._sessions() as session:
            rows = session.scalars(select(ModelWorkRow).where(
                ModelWorkRow.case_id == case_id).order_by(ModelWorkRow.id)).all()
            return [dict(row.payload) for row in rows]

    def append_history(self, case_id: str, event: dict[str, Any]) -> None:
        with self._sessions.begin() as session:
            session.add(CaseHistoryRow(case_id=case_id, event=event["event"],
                                       actor_type=event["actor_type"],
                                       actor_id=event["actor_id"], at=_timestamp(event.get("at")),
                                       payload=event.get("payload", {})))

    def get_history(self, case_id: str) -> list[dict[str, Any]]:
        with self._sessions() as session:
            rows = session.scalars(select(CaseHistoryRow).where(
                CaseHistoryRow.case_id == case_id).order_by(CaseHistoryRow.id)).all()
            return [{"event": r.event, "actor_type": r.actor_type, "actor_id": r.actor_id,
                     "at": r.at.isoformat() if r.at else "", "payload": r.payload or {}}
                    for r in rows]

    def claim_idempotency(self, key: str, body_hash: str) -> Claim:
        with self._idem_guard:
            local = self._local_idem.get(key)
            if local:
                if local["body_hash"] != body_hash:
                    raise IdempotencyConflict(key)
                return Claim(event=local["event"], first=False)
            event = threading.Event()
            with self._sessions.begin() as session:
                inserted = session.execute(
                    pg_insert(IdempotencyKeyRow)
                    .values(idempotency_key=key, body_hash=body_hash)
                    .on_conflict_do_nothing(index_elements=["idempotency_key"])
                    .returning(IdempotencyKeyRow.id)
                ).scalar_one_or_none()
                first = inserted is not None
                if not first:
                    existing = session.scalar(select(IdempotencyKeyRow).where(
                        IdempotencyKeyRow.idempotency_key == key))
                    if existing is None or existing.body_hash != body_hash:
                        raise IdempotencyConflict(key)
                    if existing.case_id:
                        event.set()
            self._local_idem[key] = {"body_hash": body_hash, "event": event}
            return Claim(event=event, first=first)

    def complete_idempotency(self, key: str, case_id: str) -> None:
        with self._sessions.begin() as session:
            row = session.scalar(select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.idempotency_key == key))
            if row:
                row.case_id = case_id
        with self._idem_guard:
            local = self._local_idem.get(key)
            if local:
                local["case_id"] = case_id
                local["event"].set()

    def release_idempotency(self, key: str) -> None:
        with self._sessions.begin() as session:
            session.execute(delete(IdempotencyKeyRow).where(
                IdempotencyKeyRow.idempotency_key == key,
                IdempotencyKeyRow.case_id.is_(None),
            ))
        with self._idem_guard:
            local = self._local_idem.pop(key, None)
            if local:
                local["event"].set()

    def idempotent_case_id(self, key: str) -> str | None:
        with self._sessions() as session:
            row = session.scalar(select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.idempotency_key == key))
            return row.case_id if row else None
