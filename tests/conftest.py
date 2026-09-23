from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.app import create_app  # noqa: E402
from app.api.container import build_container  # noqa: E402
from app.persistence.reader import (  # noqa: E402
    ChatLog, ChatMessage, FareBreakdown, FareComponent, GpsSamples, Profile,
    RideRecord, RouteRecord,
)
from app.persistence.reader import DatabaseUnavailable  # noqa: E402
from app.settings import Settings  # noqa: E402


class QAFixtureReader:
    def __init__(self):
        self.rides = {}
        self.routes = {}
        self.gps = {}
        self.chats = {}
        self.fares = {}
        self.profiles = {}
        self.available = True

    def _guard(self):
        if not self.available:
            raise DatabaseUnavailable("QA reader unavailable")

    def get_ride(self, key): self._guard(); return self.rides.get(key)
    def get_route(self, key): self._guard(); return self.routes.get(key)
    def get_gps_samples(self, key): self._guard(); return self.gps.get(key)
    def get_chat_log(self, key): self._guard(); return self.chats.get(key)
    def get_fare_breakdown(self, key): self._guard(); return self.fares.get(key)
    def get_profile(self, key): self._guard(); return self.profiles.get(key)
    def search_archive(self, category, features, limit): self._guard(); return []
    def get_archive_case(self, key): self._guard(); raise AssertionError("not used")


def seed_route(reader, ride_id="RIDE-000001"):
    reader.rides[ride_id] = RideRecord(
        ride_id=ride_id, rider_id="USR-R-000001", driver_id="USR-D-000001",
        booked_at="2026-09-22T06:00:00Z", completed_at="2026-09-22T06:40:00Z",
        status="completed", quoted_fare_cents=1000, charged_fare_cents=900,
        planned_distance_km=10, estimated_duration_s=1500)
    reader.routes[ride_id] = RouteRecord(
        ride_id=ride_id, planned_distance_km=10, actual_distance_km=14.83,
        planned_duration_s=1500, actual_duration_s=1700)
    reader.gps[ride_id] = GpsSamples(ride_id=ride_id, samples=[], min_distance_to_pickup_m=5)
    reader.fares[ride_id] = FareBreakdown(
        ride_id=ride_id, components=[FareComponent(name="base", amount_cents=900)],
        cancellation_fee_cents=0)
    reader.profiles["USR-R-000001"] = Profile(user_id="USR-R-000001", account_age_days=400, avg_rating=4.8)
    reader.profiles["USR-D-000001"] = Profile(user_id="USR-D-000001", account_age_days=800, avg_rating=4.9)


def seed_no_show(reader, ride_id="RIDE-000002"):
    reader.rides[ride_id] = RideRecord(
        ride_id=ride_id, rider_id="USR-R-000002", driver_id="USR-D-000002",
        booked_at="2026-09-22T06:00:00Z", status="cancelled", quoted_fare_cents=0,
        charged_fare_cents=0, driver_waited_seconds=360)
    reader.routes[ride_id] = RouteRecord(ride_id=ride_id, planned_distance_km=0, actual_distance_km=0, planned_duration_s=0, actual_duration_s=0)
    reader.gps[ride_id] = GpsSamples(ride_id=ride_id, samples=[], min_distance_to_pickup_m=20)
    reader.chats[ride_id] = ChatLog(ride_id=ride_id, messages=[ChatMessage(seq=1, role="driver", at="2026-09-22T06:05:00Z", text="here", kind="call_attempt")])
    reader.fares[ride_id] = FareBreakdown(ride_id=ride_id, components=[FareComponent(name="cancellation", amount_cents=0)], cancellation_fee_cents=0)
    reader.profiles["USR-R-000002"] = Profile(user_id="USR-R-000002", account_age_days=300, avg_rating=4.7)
    reader.profiles["USR-D-000002"] = Profile(user_id="USR-D-000002", account_age_days=500, avg_rating=4.9)


@pytest.fixture
def reader():
    r = QAFixtureReader(); seed_route(r); seed_no_show(r); return r


@pytest.fixture
def client(reader):
    settings = Settings(model_provider="deterministic_mock", model_name="qa-mock", policy_path=str(ROOT / "backend/tests/fixtures/policy/ryde-policy-0.1.0.json"))
    return TestClient(create_app(build_container(reader=reader, settings=settings)))
