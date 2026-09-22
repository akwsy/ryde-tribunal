"""I-8 — external information is quarantined.

With the external provider forced to fail, the API still returns a ruling whose
external_findings is empty and external_unavailable is true, and nothing is fabricated.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import build_container
from app.evidence.external import FailingExternalSource
from tests.conftest import make_settings
from tests.fixtures.cases import route_case
from tests.fixtures.reader import FixtureReader


def test_external_failure_still_returns_ruling_with_empty_findings(rid):
    reader = FixtureReader()
    route_case(reader, case_id="DSP-000045", ride_id="RIDE-1",
               planned_km=10.0, actual_km=15.0, quoted_cents=1000, charged_cents=1500)
    container = build_container(
        reader=reader, settings=make_settings(), external=FailingExternalSource()
    )
    client = TestClient(create_app(container))
    r = client.post("/api/v1/disputes/DSP-000045/adjudicate", headers={"X-Reviewer-Id": rid})
    assert r.status_code == 200
    body = r.json()
    # A ruling STILL returned…
    assert body["judge"]["ruling_type"] in ("refund", "no_action", "compensation")
    # …with quarantine intact.
    assert body["external_findings"] == []
    assert body["external_unavailable"] is True


def test_external_disabled_is_not_unavailable(client, reader, rid):
    # Default DisabledExternalSource: feature off, not a failure.
    route_case(reader, case_id="DSP-000046", ride_id="RIDE-2",
               planned_km=10.0, actual_km=15.0, quoted_cents=1000, charged_cents=1500)
    body = client.post("/api/v1/disputes/DSP-000046/adjudicate",
                       headers={"X-Reviewer-Id": rid}).json()
    assert body["external_findings"] == []
    assert body["external_unavailable"] is False
