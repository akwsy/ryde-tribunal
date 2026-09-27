from __future__ import annotations

import csv
import io
import json
import zipfile

import pytest

from archive_importer.bundle import ArchiveBundleError, CSV_COLUMNS, load_bundle


def _csv(columns: set[str], rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=sorted(columns))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def _bundle(path, *, filed_at="2026-07-10T09:00:00+08:00", filed_by="rider", categories=None, rider_average="4.70"):
    users = [
        {"source_user_key": "r", "role": "rider", "display_name": "Synthetic rider", "account_age_days": "50", "average_rating": rider_average, "total_trips": "3"},
        {"source_user_key": "d", "role": "driver", "display_name": "Synthetic driver", "account_age_days": "80", "average_rating": "4.50", "total_trips": "7"},
    ]
    trips = [{
        "source_trip_key": "t", "rider_source_user_key": "r", "driver_source_user_key": "d",
        "trip_status": "completed", "trip_at": "2026-07-09T08:50:00+08:00",
        "requested_at": "2026-07-09T08:50:00+08:00", "accepted_at": "2026-07-09T08:52:00+08:00",
        "pickup_at": "2026-07-09T08:57:00+08:00", "dropoff_at": "2026-07-09T09:00:00+08:00",
        "service_tier": "standard", "quoted_distance_meters": "5000", "quoted_duration_seconds": "600",
        "quoted_fare_cents": "1200", "fare_cents": "1200", "currency": "SGD",
        "rider_rating": "4.50", "driver_rating": "4.70",
        "fare_breakdown": '{"base_fare_cents":350}', "pricing_structure": '{"service_tier":"standard"}',
        "pickup_details": '{"label":"Orchard","lat":1.30,"lon":103.83}',
        "dropoff_details": '{"label":"CBD","lat":1.28,"lon":103.85}',
        "gps_data": '[{"recorded_at":"2026-07-09T08:58:00+08:00","lat":1.30,"lon":103.83}]',
    }]
    cases = [{
        "source_case_key": "c", "source_trip_key": "t", "filing_user_source_key": "r",
        "category": (categories or ["fare_calculation"])[0], "subject": "Synthetic case", "filed_by": filed_by,
        "created_at": filed_at, "policy_version": "ryde-policy-0.1.1", "primary_classification": "fare_calculation",
        "secondary_classifications": "[]", "monetary_impact_cents": "500", "fraud_risk": "0.1",
    }]
    rulings = [
        {"source_case_key": "c", "stage": "model_proposed", "origin": "agent", "verdict": "refund", "ruling_type": "refund", "action_description": "Synthetic proposal", "amount_cents": "500", "currency": "SGD", "confidence": "0.7", "decided_at": filed_at},
        {"source_case_key": "c", "stage": "reviewer_approved", "origin": "human", "verdict": "refund", "ruling_type": "refund", "action_description": "Synthetic approved ruling", "amount_cents": "500", "currency": "SGD", "confidence": "0.8", "decided_at": filed_at},
    ]
    reviews = [{
        "source_case_key": "c", "reason_code": "goodwill", "rationale": "Synthetic reviewer note",
        "agreed_with_agent": "true", "changed_fields": "[]", "reweighted_evidence": "[]", "reviewed_at": filed_at,
    }]
    evidence = [{
        "source_evidence_key":"ev-1", "source_case_key":"c", "evidence_class":"gps_telemetry",
        "source":"system_record", "recorded_at":filed_at,
        "provenance":'{"collector":"synthetic"}', "verification":'{"status":"verified"}',
        "visibility":"both", "payload":'{"summary":"GPS supports route"}',
    }]
    rows = {"users.csv": users, "trips.csv": trips, "cases.csv": cases, "rulings.csv": rulings,
            "reviews.csv": reviews, "evidence.csv": evidence}
    members = {"manifest.json": json.dumps({"format_version": "1", "source_system": "synthetic-test", "synthetic": True}).encode()}
    members.update({name: _csv(CSV_COLUMNS[name], value) for name, value in rows.items()})
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def test_valid_archive_bundle_preserves_roles_and_separate_rulings(tmp_path):
    path = tmp_path / "archive.zip"
    _bundle(path)
    bundle = load_bundle(path)
    assert len(bundle.tables["cases.csv"]) == 1
    assert {r["stage"] for r in bundle.tables["rulings.csv"]} == {"model_proposed", "reviewer_approved"}
    assert bundle.tables["trips.csv"][0]["pickup_details"] == '{"label":"Orchard","lat":1.30,"lon":103.83}'
    assert bundle.tables["trips.csv"][0]["quoted_fare_cents"] == "1200"
    assert bundle.tables["trips.csv"][0]["gps_data"].startswith("[")
    evidence = bundle.tables["evidence.csv"][0]
    assert evidence["source"] == "system_record"
    assert json.loads(evidence["provenance"]) == {"collector": "synthetic"}
    assert json.loads(evidence["verification"]) == {"status": "verified"}
    assert evidence["visibility"] == "both"
    assert json.loads(evidence["payload"]) == {"summary": "GPS supports route"}


def test_rejects_archive_case_filed_before_linked_trip(tmp_path):
    path = tmp_path / "archive.zip"
    _bundle(path, filed_at="2026-07-08T09:00:00+08:00")
    with pytest.raises(ArchiveBundleError, match="strictly after its trip"):
        load_bundle(path)


def test_rejects_case_filer_role_mismatch(tmp_path):
    path = tmp_path / "archive.zip"
    _bundle(path, filed_by="driver")
    with pytest.raises(ArchiveBundleError, match="filer must match"):
        load_bundle(path)


def test_rejects_archive_user_average_that_does_not_match_received_rating(tmp_path):
    path = tmp_path / "archive.zip"
    _bundle(path, rider_average="4.25")
    with pytest.raises(ArchiveBundleError, match="average must match received trip ratings"):
        load_bundle(path)


def test_rejects_missing_human_review_row(tmp_path):
    path = tmp_path / "archive.zip"
    _bundle(path)
    with zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist() if name != "reviews.csv"}
    path.unlink()
    with zipfile.ZipFile(path, "a") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
        archive.writestr("reviews.csv", _csv(CSV_COLUMNS["reviews.csv"], []))
    with pytest.raises(ArchiveBundleError, match="reviews.csv must contain"):
        load_bundle(path)
