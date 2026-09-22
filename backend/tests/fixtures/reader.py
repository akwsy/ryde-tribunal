"""In-memory fixture reader implementing the EIGHT read-only accessor signatures (docs/02 §5).

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
        # I-2a: reject a live id before any lookup.
        assert_archive_id(archive_case_id)
        for a in self.archive:
            if a.archive_case_id == archive_case_id:
                return a
        return None
