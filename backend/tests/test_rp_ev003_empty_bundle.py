"""RP-EV-003 — a confident ruling on absent deciding evidence must be IMPOSSIBLE.

Forces an empty evidence bundle (a reader that returns no ride facts) and asserts the case
escalates with a below-threshold confidence and empty advocate citations that read as
'nothing to cite', not as 'clean'.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import build_container
from app.persistence.reader import (
    ArchiveCase,
    CaseRecord,
    ChatLog,
    FareBreakdown,
    GpsSamples,
    Profile,
    RideRecord,
    RouteRecord,
)
from tests.conftest import make_settings


class EmptyReader:
    """A reader with NO ride facts: every accessor returns None/empty. The live case still
    exists in the store, but nothing assembles into a verified bundle."""

    def get_ride(self, ride_id): return None
    def get_route(self, ride_id): return None
    def get_gps_samples(self, ride_id): return None
    def get_chat_log(self, ride_id): return None
    def get_fare_breakdown(self, ride_id): return None
    def get_profile(self, user_id): return None
    def search_archive(self, category, features, limit): return []
    def get_archive_case(self, archive_case_id): return None


def test_empty_bundle_escalates_never_confident(rid):
    container = build_container(reader=EmptyReader(), settings=make_settings())
    client = create_app(container)
    tc = TestClient(client)
    # File a route_deviation on a ride the reader knows nothing about.
    fid = tc.post("/api/v1/disputes", headers={"X-Reviewer-Id": rid},
                  json={"category": "route_deviation", "ride_id": "RIDE-000999",
                        "filed_by": "rider", "subject": "x", "description": "y"}).json()["case_id"]
    body = tc.post(f"/api/v1/disputes/{fid}/adjudicate", headers={"X-Reviewer-Id": rid}).json()

    # A confident ruling on no evidence is impossible: escalated, below threshold.
    assert body["status"] == "escalated"
    assert body["judge"]["confidence"] < 0.70
    reasons = body["judge"]["escalation"]["reasons"]
    assert "confidence_below_threshold" in reasons or "insufficient_or_contradictory_evidence" in reasons
    # No verified evidence to cite — and that reads as absence, with a human-review summary.
    assert body["judge"]["evidence_references"] == [] or all(
        not r for r in body["judge"]["evidence_references"]
    )
    assert body["judge"]["escalation"]["human_review_summary"]
