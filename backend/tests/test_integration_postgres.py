"""End-to-end integration tests against a REAL PostgreSQL (the seeded ryde_tribunal database).

These SKIP cleanly when no database is configured. To run them:

    export RYDE_TEST_READ_DSN="postgresql://ryde_backend_readonly@localhost:5432/ryde_tribunal"
    cd backend && uv run pytest tests/test_integration_postgres.py -v

They exercise the PostgresReader adapter over the database package's eight accessors, the
read-only privilege boundary, and the database_unavailable path. Offline CI on
deterministic_mock is unaffected — without the env var every test here is skipped.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import build_container
from app.persistence.postgres_reader import PostgresReader
from app.persistence.reader import DatabaseUnavailable
from tests.conftest import make_settings

READ_DSN = os.getenv("RYDE_TEST_READ_DSN")
_skip = pytest.mark.skipif(READ_DSN is None, reason="set RYDE_TEST_READ_DSN to run Postgres integration tests")

# A seeded ride id (ride_data holds RIDE-000001 .. RIDE-000060).
SEEDED_RIDE = "RIDE-000001"


def _client(reader) -> TestClient:
    container = build_container(reader=reader, settings=make_settings())
    return TestClient(create_app(container))


@_skip
def test_end_to_end_against_real_postgres():
    reader = PostgresReader(READ_DSN)
    client = _client(reader)

    # The category the ride's facts support: RIDE-000001 completed with a route deviation.
    file_resp = client.post(
        "/api/v1/disputes",
        headers={"X-Reviewer-Id": "REV-1"},
        json={
            "category": "route_deviation",
            "ride_id": SEEDED_RIDE,
            "filed_by": "rider",
            "subject": "Charged more than quoted",
            "description": "The route looked much longer than what I booked.",
        },
    )
    assert file_resp.status_code == 201, file_resp.text
    case_id = file_resp.json()["case_id"]

    adj = client.post(f"/api/v1/disputes/{case_id}/adjudicate", headers={"X-Reviewer-Id": "REV-1"})
    assert adj.status_code == 200, adj.text
    body = adj.json()

    # Complete CaseResult.
    assert body["judge"]["ruling_type"] in ("refund", "compensation", "no_action")
    assert 0.0 <= body["judge"]["confidence"] <= 1.0
    assert body["policy_version"] == "ryde-policy-0.1.0"
    assert body["judge"]["measurements"], "no measurements recorded"

    # The reasoning must have evidence to stand on (the defect this test now guards):
    # advocates cited real records, and the ruling references them.
    assert len(body["advocates"]["rider"]["claims"]) > 0, "rider cited nothing"
    assert len(body["advocates"]["driver"]["claims"]) > 0, "driver cited nothing"
    rider_citations = sum(len(c["citations"]) for c in body["advocates"]["rider"]["claims"])
    assert rider_citations > 0, "rider produced no citations"
    refs = body["judge"]["evidence_references"]
    assert refs, "judge.evidence_references is empty"

    # EXHAUSTIVE: every id in evidence_references AND every id cited by either advocate must
    # resolve 200 with a matching case_id — checked with the id ONLY (no case_id query param),
    # scoping resolved server-side. Checking only the first id is what let the empty-bundle
    # defect through, so iterate all of them.
    cited_ids = {
        cit["evidence_id"]
        for side in ("rider", "driver")
        for claim in body["advocates"][side]["claims"]
        for cit in claim["citations"]
    }
    all_ids = set(refs) | cited_ids
    assert all_ids, "no evidence ids referenced or cited"
    for eid in sorted(all_ids):
        r = client.get(f"/api/v1/evidence/{eid}")
        assert r.status_code == 200, f"evidence {eid} not resolvable ({r.status_code})"
        assert r.json()["case_id"] == case_id, f"evidence {eid} case_id mismatch"

    # A non-existent id is a clean 404 (not 422, not 500).
    missing = client.get("/api/v1/evidence/EV-999999")
    assert missing.status_code == 404, f"EV-999999 returned {missing.status_code}, expected 404"

    # Each rider citation's observed_value equals the ride_data row it names.
    route = reader.get_route(SEEDED_RIDE)
    ride = reader.get_ride(SEEDED_RIDE)
    row = {
        "actual_distance_km": route.actual_distance_km,
        "planned_distance_km": route.planned_distance_km,
        "quoted_fare_cents": ride.quoted_fare_cents,
        "charged_fare_cents": ride.charged_fare_cents,
    }
    for claim in body["advocates"]["rider"]["claims"]:
        for cit in claim["citations"]:
            field = cit["field_path"].split(".")[-1]
            if field in row:
                a, b_ = cit["observed_value"], row[field]
                if isinstance(a, (int, float)) and isinstance(b_, (int, float)):
                    assert abs(float(a) - float(b_)) < 1e-6, f"{field}: {a} != {b_}"

    # Evidence references trace back to real ride_data rows via the measurements.
    m = body["judge"]["measurements"]
    assert abs(m["actual_distance_km"] - route.actual_distance_km) < 1e-6
    assert abs(m["planned_distance_km"] - route.planned_distance_km) < 1e-6
    # case_facts denormalizes the real ride header.
    assert body["case_facts"]["charged_fare_cents"] == ride.charged_fare_cents


@_skip
def test_readonly_role_cannot_write_ride_data():
    """The read connection holds SELECT only on ride_data. An INSERT must be refused by
    PostgreSQL itself — the strongest possible guarantee of the boundary (contract §5)."""
    with psycopg.connect(READ_DSN) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO ride_data.rides (ride_id) VALUES ('RIDE-999999')"
            )
        conn.rollback()


@_skip
def test_database_unavailable_returns_error_not_ruling():
    """With Postgres unreachable, adjudication returns database_unavailable and never a ruling."""
    bad_reader = PostgresReader("postgresql://ryde_backend_readonly@127.0.0.1:5999/nope")
    client = _client(bad_reader)
    file_resp = client.post(
        "/api/v1/disputes",
        headers={"X-Reviewer-Id": "REV-1"},
        json={"category": "route_deviation", "ride_id": SEEDED_RIDE, "filed_by": "rider",
              "subject": "x", "description": "y"},
    )
    case_id = file_resp.json()["case_id"]
    adj = client.post(f"/api/v1/disputes/{case_id}/adjudicate", headers={"X-Reviewer-Id": "REV-1"})
    assert adj.status_code == 503
    assert adj.json()["error"]["code"] == "database_unavailable"
    assert "judge" not in adj.json()
