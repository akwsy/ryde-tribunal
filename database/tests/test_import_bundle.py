from __future__ import annotations

import csv
import io
import json
import zipfile

import pytest

from importer.bundle import BundleValidationError, load_bundle
from importer.persist import _evidence_values


HEADERS = {
    "users.csv": ["company_user_id", "role", "name"],
    "profiles.csv": [
        "company_user_id", "account_age_days", "total_trips", "avg_rating",
        "dispute_history_total", "dispute_history_upheld", "dispute_history_rejected",
        "dispute_history_upheld_against", "fraud_flags", "fraud_flag_details",
        "payment_method", "vehicle",
    ],
    "trips.csv": [
        "company_trip_id", "company_rider_id", "company_driver_id", "pickup_location_name",
        "pickup_lat", "pickup_lng", "dropoff_location_name", "dropoff_lat", "dropoff_lng",
        "scheduled_time", "driver_arrival_time", "driver_wait_start", "cancellation_time",
        "cancellation_fee", "cancellation_reason",
    ],
    "gps_telemetry.csv": [
        "company_trip_id", "sequence_no", "timestamp", "lat", "lng", "speed_kmh", "status",
    ],
    "chat_logs.csv": ["company_trip_id", "sequence_no", "timestamp", "sender", "type", "content"],
    "app_events.csv": ["company_trip_id", "sequence_no", "timestamp", "event_type", "details"],
}


def _csv(headers: list[str], rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode()


def _make_zip(path, extra: dict[str, bytes] | None = None) -> None:
    members = {
        "manifest.json": json.dumps({"format_version": "1", "source_system": "example-company"}).encode(),
        "users.csv": _csv(HEADERS["users.csv"], [
            ["src-user-r", "rider", "Example Rider"],
            ["src-user-d", "driver", "Example Driver"],
        ]),
        "profiles.csv": _csv(HEADERS["profiles.csv"], [
            ["src-user-r", "10", "4", "4.5", "0", "0", "0", "0", "0", "", "", ""],
            ["src-user-d", "10", "4", "4.5", "0", "0", "0", "0", "0", "", "", ""],
        ]),
        "trips.csv": _csv(HEADERS["trips.csv"], [[
            "src-trip", "src-user-r", "src-user-d", "Sample Pickup", "1.3", "103.8",
            "Sample Dropoff", "1.2", "103.9", "2026-09-13T08:45:00+08:00", "", "", "",
            "0.00", "",
        ]]),
        "gps_telemetry.csv": _csv(HEADERS["gps_telemetry.csv"], []),
        "chat_logs.csv": _csv(HEADERS["chat_logs.csv"], []),
        "app_events.csv": _csv(HEADERS["app_events.csv"], []),
    }
    members.update(extra or {})
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def test_loads_complete_bundle_and_preserves_source_strings(tmp_path):
    archive = tmp_path / "bundle.zip"
    _make_zip(archive, {
        "gps_telemetry.csv": _csv(HEADERS["gps_telemetry.csv"], [[
            "src-trip", "1", "2026-09-13T08:43:00+08:00", "1.2847", "103.8382", "0", "arrived",
        ]]),
    })

    bundle = load_bundle(archive)

    assert bundle.manifest["format_version"] == "1"
    assert bundle.tables["trips.csv"][0]["company_trip_id"] == "src-trip"
    assert bundle.tables["gps_telemetry.csv"][0]["lat"] == "1.2847"


def test_validates_two_opposite_participant_ratings_and_synthetic_marker(tmp_path):
    archive = tmp_path / "rated.zip"
    trip_headers = HEADERS["trips.csv"] + ["ride_status"]
    _make_zip(archive, {
        "manifest.json": json.dumps({"format_version": "1", "source_system": "synthetic-seed", "synthetic": True}).encode(),
        "trips.csv": _csv(trip_headers, [[
            "src-trip", "src-user-r", "src-user-d", "P", "1.3", "103.8", "D", "1.2", "103.9",
            "2026-07-01T08:00:00+08:00", "", "", "", "0.00", "", "completed",
        ]]),
        "ratings.csv": _csv(["company_trip_id", "company_rated_user_id", "rating_from_role", "rating", "rated_at"], [
            ["src-trip", "src-user-r", "driver", "4.50", "2026-07-01T09:00:00+08:00"],
            ["src-trip", "src-user-d", "rider", "4.50", "2026-07-01T09:00:00+08:00"],
        ]),
    })

    bundle = load_bundle(archive)

    assert bundle.manifest["synthetic"] is True
    assert len(bundle.tables["ratings.csv"]) == 2


def test_rejects_ratings_for_cancelled_trip(tmp_path):
    archive = tmp_path / "rated-cancelled.zip"
    trip_headers = HEADERS["trips.csv"] + ["ride_status"]
    _make_zip(archive, {
        "trips.csv": _csv(trip_headers, [[
            "src-trip", "src-user-r", "src-user-d", "P", "1.3", "103.8", "D", "1.2", "103.9",
            "2026-07-01T08:00:00+08:00", "", "", "", "0.00", "", "cancelled_after_arrival",
        ]]),
        "ratings.csv": _csv(["company_trip_id", "company_rated_user_id", "rating_from_role", "rating", "rated_at"], [
            ["src-trip", "src-user-r", "driver", "4.50", "2026-07-01T09:00:00+08:00"],
            ["src-trip", "src-user-d", "rider", "4.50", "2026-07-01T09:00:00+08:00"],
        ]),
    })
    with pytest.raises(BundleValidationError, match="cancelled trip"):
        load_bundle(archive)


def test_blank_source_sequences_preserve_csv_order_and_allow_metadata(tmp_path):
    archive = tmp_path / "bundle.zip"
    metadata_headers = [
        "record_type", "company_trip_id", "company_user_id", "sequence_no",
        "verification_status", "verified_by", "verified_at", "evidence_source",
    ]
    gps_headers = [name for name in HEADERS["gps_telemetry.csv"] if name != "sequence_no"]
    chat_headers = [name for name in HEADERS["chat_logs.csv"] if name != "sequence_no"]
    _make_zip(archive, {
        "gps_telemetry.csv": _csv(gps_headers, [
            ["src-trip", "2026-09-13T08:43:00+08:00", "1.2847", "103.8382", "0", "arrived"],
            ["src-trip", "2026-09-13T08:44:00+08:00", "1.2848", "103.8383", "1", "moving"],
        ]),
        "chat_logs.csv": _csv(chat_headers, [[
            "src-trip", "2026-09-13T08:43:30+08:00", "driver", "call", "Attempted to call rider",
        ]]),
        "evidence_metadata.csv": _csv(metadata_headers, [[
            "gps_telemetry", "src-trip", "", "0", "verified", "reviewer", "", "operator review",
        ]]),
    })

    bundle = load_bundle(archive)
    first = bundle.tables["gps_telemetry.csv"][0]
    assert bundle.tables["gps_telemetry.csv"][1]["sequence_no"] == ""
    assert bundle.tables["chat_logs.csv"][0]["type"] == "call"
    assert first["sequence_no"] == ""
    metadata = {
        ("gps_telemetry", "src-trip", "", "0"): bundle.tables["evidence_metadata.csv"][0],
    }
    status, _, _, _, provenance = _evidence_values(
        metadata,
        record_type="gps_telemetry",
        source_system="example-company",
        source_file="gps_telemetry.csv",
        company_trip_id="src-trip",
        sequence_no="0",
        source_sequence_no=first["sequence_no"],
    )
    assert status == "verified"
    assert provenance["sequence_no"] == 0
    assert provenance["sequence_no_origin"] == "csv_row_order"
    assert "source_sequence_no" not in provenance


def test_rejects_duplicate_source_trip_ids_before_import(tmp_path):
    archive = tmp_path / "bundle.zip"
    duplicate_rows = [[
        "src-trip", "src-user-r", "src-user-d", "P", "1.3", "103.8", "D", "1.2", "103.9",
        "2026-09-13T08:45:00+08:00", "", "", "", "0.00", "",
    ]] * 2
    _make_zip(archive, {"trips.csv": _csv(HEADERS["trips.csv"], duplicate_rows)})

    with pytest.raises(BundleValidationError, match="duplicate company_trip_id"):
        load_bundle(archive)


def test_rejects_unresolved_user_reference(tmp_path):
    archive = tmp_path / "bundle.zip"
    _make_zip(archive, {
        "trips.csv": _csv(HEADERS["trips.csv"], [[
            "src-trip", "missing-rider", "src-user-d", "P", "1.3", "103.8", "D", "1.2", "103.9",
            "2026-09-13T08:45:00+08:00", "", "", "", "0.00", "",
        ]]),
    })

    with pytest.raises(BundleValidationError, match="references a user absent"):
        load_bundle(archive)


def test_rejects_user_role_mismatch_for_trip_party(tmp_path):
    archive = tmp_path / "bundle.zip"
    _make_zip(archive, {
        "trips.csv": _csv(HEADERS["trips.csv"], [[
            "src-trip", "src-user-d", "src-user-d", "P", "1.3", "103.8", "D", "1.2", "103.9",
            "2026-09-13T08:45:00+08:00", "", "", "", "0.00", "",
        ]]),
    })

    with pytest.raises(BundleValidationError, match="company_rider_id must reference a rider"):
        load_bundle(archive)


def test_rejects_evidence_metadata_for_unknown_evidence_sequence(tmp_path):
    archive = tmp_path / "bundle.zip"
    metadata_headers = [
        "record_type", "company_trip_id", "company_user_id", "sequence_no",
        "verification_status", "verified_by", "verified_at", "evidence_source",
    ]
    _make_zip(archive, {
        "evidence_metadata.csv": _csv(metadata_headers, [[
            "gps_telemetry", "src-trip", "", "42", "", "", "", "",
        ]]),
    })

    with pytest.raises(BundleValidationError, match="does not reference a matching evidence record"):
        load_bundle(archive)


def test_rejects_dispute_ticket_member(tmp_path):
    archive = tmp_path / "bundle.zip"
    _make_zip(archive, {"dispute_ticket.csv": b"company_trip_id\nsrc-trip\n"})

    with pytest.raises(BundleValidationError, match="ZIP members invalid"):
        load_bundle(archive)
