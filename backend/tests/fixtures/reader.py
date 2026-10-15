"""In-memory fixture reader implementing the database's read-only accessor signatures.

Tests build their own synthetic ride/route/gps/chat/fare/profile data (which is `ride_data`)
and hand it here, plus archived precedent. This is the backend's own fixture layer — it does
NOT read the database specialist's schema, which does not exist yet. Integration replaces it
with the real Postgres reader at the same seam. It exposes NO live-case accessor (the live
case lives in the backend `tribunal` store), carries no outcome fields on live data (I-2), and
its archive accessor rejects a live id (I-2a).
"""

from __future__ import annotations

from typing import Any

from app.persistence.reader import (
    ArchiveCase,
    ArchiveHistoryRecord,
    ChatLog,
    DatabaseUnavailable,
    FareBreakdown,
    GpsSamples,
    Profile,
    RideRecord,
    RouteRecord,
    assert_archive_id,
)


class FixtureReader:
    def __init__(self) -> None:
        self.rides: dict[str, RideRecord] = {}
        self.routes: dict[str, RouteRecord] = {}
        self.gps: dict[str, GpsSamples] = {}
        self.chats: dict[str, ChatLog] = {}
        self.app_events: dict[str, list] = {}
        self.fares: dict[str, FareBreakdown] = {}
        self.profiles: dict[str, Profile] = {}
        self.archive: list[ArchiveCase] = []
        self.available = True

    def _guard(self) -> None:
        if not self.available:
            raise DatabaseUnavailable("fixture reader marked unavailable")

    def get_ride(self, ride_id: str) -> RideRecord | None:
        self._guard()
        return self.rides.get(ride_id)

    def get_route(self, ride_id: str) -> RouteRecord | None:
        self._guard()
        return self.routes.get(ride_id)

    def get_gps_samples(self, ride_id: str) -> GpsSamples | None:
        self._guard()
        return self.gps.get(ride_id)

    def get_chat_log(self, ride_id: str) -> ChatLog | None:
        self._guard()
        return self.chats.get(ride_id)

    def get_app_events(self, ride_id: str):
        self._guard()
        return self.app_events.get(ride_id, [])

    def get_fare_breakdown(self, ride_id: str) -> FareBreakdown | None:
        self._guard()
        return self.fares.get(ride_id)

    def get_profile(self, user_id: str) -> Profile | None:
        self._guard()
        return self.profiles.get(user_id)

    def search_archive(
        self, category: str, features: dict[str, Any], limit: int
    ) -> list[ArchiveCase]:
        self._guard()
        return [a for a in self.archive if a.category == category][:limit]

    def get_archive_case(self, archive_case_id: str) -> ArchiveCase | None:
        self._guard()
        # The accessor remains archive-list-only even though IDs share canonical syntax.
        assert_archive_id(archive_case_id)
        for a in self.archive:
            if a.archive_case_id == archive_case_id:
                if isinstance(a, ArchiveHistoryRecord):
                    decision = {
                        "verdict": a.verdict,
                        "ruling_type": a.ruling_type,
                        "recommended_action_description": a.recommended_action,
                        "recommended_amount": {
                            "amount_cents": a.amount_cents,
                            "currency": a.currency,
                        },
                        "confidence": a.confidence,
                        "decision_origin": a.decision_origin,
                        "decided_at": a.created_at,
                    }
                    return ArchiveCase(
                        archive_case_id=a.archive_case_id,
                        archive_ride_id=a.archive_ride_id,
                        category=a.category,
                        ruling_type=a.ruling_type,
                        recommended_action=a.recommended_action,
                        confidence=a.confidence or 0.0,
                        decision_origin=a.decision_origin,
                        policy_version=a.policy_version,
                        was_overridden=a.human_reviewed,
                        rulings=a.rulings,
                        archive_record={
                            "archive_case_id": a.archive_case_id,
                            "archive_ride_id": a.archive_ride_id,
                            "category": a.category,
                            "subject": a.subject,
                            "filed_by": a.filed_by,
                            "created_at": a.created_at,
                            "policy_version": a.policy_version,
                            "synthetic": a.synthetic,
                            "decision": decision,
                            "rulings": a.rulings,
                            "human_review": {"human_reviewed": a.human_reviewed},
                        },
                    )
                return a
        return None

    def list_archive_disputes(
        self, limit: int | None = 200
    ) -> list[ArchiveHistoryRecord]:
        self._guard()
        results = []
        archive_items = self.archive if limit is None else self.archive[:limit]
        for index, item in enumerate(archive_items):
            if isinstance(item, ArchiveHistoryRecord):
                results.append(item)
                continue
            results.append(ArchiveHistoryRecord(
                archive_case_id=item.archive_case_id,
                archive_ride_id=f"RIDE-{900001 + index:06d}",
                category=item.category,
                subject=f"Archived {item.category.replace('_', ' ')} dispute",
                filed_by="rider",
                created_at="2026-08-01T10:00:00Z",
                policy_version=item.policy_version,
                verdict="refund" if item.ruling_type == "refund" else item.ruling_type,
                ruling_type=item.ruling_type,
                recommended_action=item.recommended_action,
                amount_cents=500,
                currency="SGD",
                confidence=item.confidence,
                decision_origin=item.decision_origin,
                human_reviewed=item.was_overridden,
                rulings=item.rulings or [{
                    "stage": "reviewer_approved" if item.decision_origin == "human" else "model_proposed",
                    "verdict": "refund" if item.ruling_type == "refund" else item.ruling_type,
                    "ruling_type": item.ruling_type,
                    "recommended_action": item.recommended_action,
                    "amount_cents": 500,
                    "currency": "SGD",
                    "confidence": item.confidence,
                    "decision_origin": item.decision_origin,
                    "decided_at": "2026-08-01T12:00:00Z",
                }],
            ))
        return results
