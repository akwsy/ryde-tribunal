from __future__ import annotations

import csv
import importlib
import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.persistence.reader import DatabaseUnavailable
from app.persistence.store import ResultStore
from tests.fixtures.cases import route_case


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def phase1_api(container):
    container.store = ResultStore()
    return TestClient(create_app(container)), container.store


def _csv(headers: list[str], rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode()


def _zip_bytes() -> bytes:
    members = {
        "manifest.json": json.dumps({"format_version": "1", "source_system": "fake-export"}).encode(),
        "users.csv": _csv(["company_user_id", "role", "name"], [
            ["fake-rider", "rider", "Fake Rider"], ["fake-driver", "driver", "Fake Driver"],
        ]),
        "profiles.csv": _csv([
            "company_user_id", "account_age_days", "total_trips", "avg_rating",
            "dispute_history_total", "dispute_history_upheld", "dispute_history_rejected",
            "dispute_history_upheld_against", "fraud_flags", "fraud_flag_details",
            "payment_method", "vehicle",
        ], [
            [user, "20", "4", "4.5", "0", "0", "0", "0", "0", "", "", ""]
            for user in ("fake-rider", "fake-driver")
        ]),
        "trips.csv": _csv([
            "company_trip_id", "company_rider_id", "company_driver_id", "pickup_location_name",
            "pickup_lat", "pickup_lng", "dropoff_location_name", "dropoff_lat", "dropoff_lng",
            "scheduled_time", "driver_arrival_time", "driver_wait_start", "cancellation_time",
            "cancellation_fee", "cancellation_reason",
        ], [[
            "fake-trip", "fake-rider", "fake-driver", "Fake Pickup", "1.3", "103.8",
            "Fake Dropoff", "1.2", "103.9", "2026-09-13T08:45:00+08:00", "", "", "", "0.00", "",
        ]]),
        "gps_telemetry.csv": _csv([
            "company_trip_id", "sequence_no", "timestamp", "lat", "lng", "speed_kmh", "status",
        ], [["fake-trip", "", "2026-09-13T08:43:00+08:00", "1.3", "103.8", "0", "arrived"]]),
        "chat_logs.csv": _csv([
            "company_trip_id", "sequence_no", "timestamp", "sender", "type", "content",
        ], [["fake-trip", "", "2026-09-13T08:43:30+08:00", "driver", "message", "Fake message"]]),
        "app_events.csv": _csv([
            "company_trip_id", "sequence_no", "timestamp", "event_type", "details",
        ], [["fake-trip", "", "2026-09-13T08:44:00+08:00", "pickup_attempt", "Fake event"]]),
    }
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
    return target.getvalue()


def test_trip_search_returns_picker_fields_and_internal_id(phase1_api, reader, monkeypatch):
    client, _store = phase1_api
    calls = []

    def search(query, limit):
        calls.append((query, limit))
        return [{
            "ride_id": "RIDE-123456", "company_trip_id": "source-ride-9",
            "booked_at": "2026-09-13T00:45:00Z", "ride_status": "completed",
            "pickup_label": "Joo Chiat", "dropoff_label": "Tampines",
            "rider_name": "Example Rider", "driver_name": "Example Driver",
            "source_system": "example-source",
        }]

    monkeypatch.setattr(reader, "search_rides", search, raising=False)
    response = client.get("/api/v1/trips", params={"query": "Joo Chiat", "limit": 7})
    assert response.status_code == 200
    assert calls == [("Joo Chiat", 7)]
    assert response.json() == {"items": [{
        "ride_id": "RIDE-123456", "company_trip_id": "source-ride-9",
        "booked_at": "2026-09-13T00:45:00Z", "status": "completed",
        "pickup_label": "Joo Chiat", "dropoff_label": "Tampines",
        "rider_name": "Example Rider", "driver_name": "Example Driver",
    }]}


def test_trip_search_maps_database_unavailable_to_503(phase1_api, reader, monkeypatch):
    client, _store = phase1_api

    def fail(_query, _limit):
        raise DatabaseUnavailable("offline")

    monkeypatch.setattr(reader, "search_rides", fail, raising=False)
    response = client.get("/api/v1/trips")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


def test_postgres_reader_search_adapter_uses_database_owned_accessor(monkeypatch):
    from app.persistence import postgres_reader

    calls = []

    class SearchRow:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"ride_id": "RIDE-000123", "booked_at": None, "ride_status": "completed"}

    def search(query, limit):
        calls.append((query, limit))
        return [SearchRow()]

    monkeypatch.setattr(postgres_reader, "db_search_rides", search)
    adapter = postgres_reader.PostgresReader("postgresql://readonly:test@localhost/test-db")
    assert adapter.search_rides("pickup", 4) == [
        {"ride_id": "RIDE-000123", "booked_at": None, "ride_status": "completed"}
    ]
    assert calls == [("pickup", 4)]


def test_company_import_validates_zip_then_reports_per_type_counts(
    phase1_api, container, monkeypatch,
):
    client, _store = phase1_api
    container.settings.import_database_dsn = "postgresql://importer:secret@localhost/ryde_tribunal"
    persist = importlib.import_module("database.importer.persist")
    calls = []

    def fake_import(dsn, bundle):
        calls.append((dsn, bundle.manifest["source_system"]))
        return SimpleNamespace(
            imported_user_count=1, imported_trip_count=1,
            skipped_user_ids=("fake-rider",), skipped_trip_ids=(),
        )

    monkeypatch.setattr(persist, "import_bundle", fake_import)
    response = client.post(
        "/api/v1/imports/company-data", content=_zip_bytes(),
        headers={"X-Reviewer-Id": "REV-001", "Content-Type": "application/zip"},
    )
    assert response.status_code == 200, response.text
    assert calls == [(container.settings.import_database_dsn, "fake-export")]
    assert response.json() == {
        "source_system": "fake-export",
        "imported": {
            "users": 1, "profiles": 1, "trips": 1, "routes": 1, "fares": 1,
            "gps_telemetry": 1, "chat_logs": 1, "app_events": 1,
        },
        "skipped_duplicate_ids": {
            "users": 1, "profiles": 1, "trips": 0, "routes": 0, "fares": 0,
            "gps_telemetry": 0, "chat_logs": 0, "app_events": 0,
        },
    }


def test_company_import_rejects_invalid_zip_before_calling_writer(
    phase1_api, container, monkeypatch,
):
    client, _store = phase1_api
    container.settings.import_database_dsn = "postgresql://importer:secret@localhost/ryde_tribunal"
    persist = importlib.import_module("database.importer.persist")
    calls = []
    monkeypatch.setattr(persist, "import_bundle", lambda *_: calls.append(True))
    response = client.post(
        "/api/v1/imports/company-data", content=b"not-a-zip",
        headers={"X-Reviewer-Id": "REV-001", "Content-Type": "application/zip"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert calls == []


def test_company_import_requires_reviewer_and_enforces_configured_size_limit(
    phase1_api, container,
):
    client, _store = phase1_api
    container.settings.import_max_upload_bytes = 10
    no_reviewer = client.post(
        "/api/v1/imports/company-data", content=b"x" * 11,
        headers={"Content-Type": "application/zip"},
    )
    assert no_reviewer.status_code == 401
    too_large = client.post(
        "/api/v1/imports/company-data", content=b"x" * 11,
        headers={"X-Reviewer-Id": "REV-001", "Content-Type": "application/zip"},
    )
    assert too_large.status_code == 413


def test_company_import_needs_dedicated_import_dsn(phase1_api, container):
    client, _store = phase1_api
    container.settings.import_database_dsn = ""
    response = client.post(
        "/api/v1/imports/company-data", content=_zip_bytes(),
        headers={"X-Reviewer-Id": "REV-001", "Content-Type": "application/zip"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


def test_safety_triage_includes_review_summary_without_automated_finding(phase1_api, reader):
    client, store = phase1_api
    route_case(
        reader, store=store, case_id="DSP-000899", ride_id="RIDE-000899",
        planned_km=10, actual_km=11, quoted_cents=1000, charged_cents=1100,
    )
    filed = client.post(
        "/api/v1/disputes", headers={"X-Reviewer-Id": "REV-001"},
        json={"category": "safety_incident", "ride_id": "RIDE-000899",
              "filed_by": "rider", "subject": "Safety report", "description": "Human review."},
    )
    assert filed.status_code == 201
    result = client.post(
        f"/api/v1/disputes/{filed.json()['case_id']}/adjudicate",
        headers={"X-Reviewer-Id": "REV-001"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "pending_review"
    assert body["judge"] is None
    assert body["triage"]["final_decision_required"] is True
    assert body["evidence_audit"]["findings"] == []
    assert body["evidence_audit"]["provider"]["kind"] == "rules-engine"
    assert body["fraud_assessment"] is None
