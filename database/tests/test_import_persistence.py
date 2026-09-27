from __future__ import annotations

import csv
import io
import json
import zipfile

import psycopg

from importer.bundle import load_bundle
from importer.persist import import_bundle
from tests.test_import_bundle import HEADERS, _csv


def _write_bundle(
    path,
    *,
    source_system: str,
    users: list[list[str]],
    profiles: list[list[str]],
    trips: list[list[str]],
    gps: list[list[str]] | None = None,
    chats: list[list[str]] | None = None,
    events: list[list[str]] | None = None,
) -> None:
    members = {
        "manifest.json": json.dumps({"format_version": "1", "source_system": source_system}).encode(),
        "users.csv": _csv(HEADERS["users.csv"], users),
        "profiles.csv": _csv(HEADERS["profiles.csv"], profiles),
        "trips.csv": _csv(HEADERS["trips.csv"], trips),
        "gps_telemetry.csv": _csv(HEADERS["gps_telemetry.csv"], gps or []),
        "chat_logs.csv": _csv(HEADERS["chat_logs.csv"], chats or []),
        "app_events.csv": _csv(HEADERS["app_events.csv"], events or []),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def _profile(company_user_id: str, *, total_trips: str = "4") -> list[str]:
    return [company_user_id, "10", total_trips, "4.5", "0", "0", "0", "0", "0", "", "", ""]


def _trip(
    trip_id: str,
    rider_id: str,
    driver_id: str,
    pickup_label: str,
    *,
    cancellation_reason: str = "",
) -> list[str]:
    return [
        trip_id, rider_id, driver_id, pickup_label, "1.3000", "103.8000", "Example Dropoff",
        "1.2000", "103.9000", "2026-09-13T08:45:00+08:00", "", "", "", "0.00",
        cancellation_reason,
    ]


def _mapping(result) -> dict[tuple[str, str], str]:
    rows = csv.DictReader(io.StringIO(result.mapping_csv))
    return {(row["record_type"], row["company_source_id"]): row["internal_id"] for row in rows}


def test_import_persists_fake_rows_skips_duplicates_and_links_existing_user(
    tmp_path, monkeypatch, isolated_company_import_database: str,
) -> None:
    rider = ["fake-user-rider", "rider", "Fake Rider"]
    driver = ["fake-user-driver", "driver", "Fake Driver"]
    trip = _trip("fake-trip-1", rider[0], driver[0], "Fake Pickup")
    first_bundle_path = tmp_path / "first.zip"
    _write_bundle(
        first_bundle_path,
        source_system="fake-export-one",
        users=[rider, driver],
        profiles=[_profile(rider[0]), _profile(driver[0])],
        trips=[trip],
        gps=[["fake-trip-1", "", "2026-09-13T08:43:00+08:00", "1.2847", "103.8382", "12.5", "arrived"]],
        chats=[["fake-trip-1", "", "2026-09-13T08:43:30+08:00", "driver", "call", "Synthetic call record"]],
        events=[["fake-trip-1", "", "2026-09-13T08:44:00+08:00", "pickup_attempt", "Synthetic event"]],
    )

    first = import_bundle(isolated_company_import_database, load_bundle(first_bundle_path))
    first_ids = _mapping(first)
    assert first.imported_user_count == 2
    assert first.imported_trip_count == 1
    assert first.skipped_user_ids == ()
    assert first.skipped_trip_ids == ()
    rider_id = first_ids[("user", rider[0])]
    driver_id = first_ids[("user", driver[0])]
    ride_id = first_ids[("trip", "fake-trip-1")]
    assert rider_id.startswith("USR-R-")
    assert driver_id.startswith("USR-D-")
    assert ride_id.startswith("RIDE-")
    assert rider[0] in first.mapping_csv and "Fake Rider" not in first.mapping_csv

    monkeypatch.setenv("DATABASE_URL", isolated_company_import_database)
    from reader import search_rides

    selected = search_rides("fake-trip-1", limit=5)
    assert len(selected) == 1
    assert selected[0].ride_id == ride_id
    assert selected[0].company_trip_id == "fake-trip-1"
    assert selected[0].source_system == "fake-export-one"
    assert selected[0].pickup_label == "Fake Pickup"
    assert selected[0].rider_name == "Fake Rider"
    assert selected[0].driver_name == "Fake Driver"
    assert search_rides("Fake Rider", limit=5)[0].ride_id == ride_id
    assert search_rides("", limit=5)[0].ride_id == ride_id

    with psycopg.connect(isolated_company_import_database) as conn:
        assert conn.execute("SELECT count(*) FROM ride_data.users WHERE synthetic IS FALSE").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM ride_data.rides WHERE synthetic IS FALSE").fetchone()[0] == 1
        gps = conn.execute(
            "SELECT sequence_no, speed_kmh, verification_status, provenance FROM ride_data.ride_gps_samples WHERE ride_id = %s",
            (ride_id,),
        ).fetchone()
        chat = conn.execute(
            "SELECT sequence_no, message_type, message_text, verification_status FROM ride_data.ride_chat_messages WHERE ride_id = %s",
            (ride_id,),
        ).fetchone()
        event = conn.execute(
            "SELECT sequence_no, event_type, details, verification_status FROM ride_data.ride_app_events WHERE ride_id = %s",
            (ride_id,),
        ).fetchone()
        assert gps[0] == 0
        assert str(gps[1]) == "12.5"
        assert gps[2] == "unverified"
        assert gps[3]["sequence_no"] == 0
        assert gps[3]["sequence_no_origin"] == "csv_row_order"
        assert chat == (0, "call", "Synthetic call record", "unverified")
        assert event == (0, "pickup_attempt", "Synthetic event", "unverified")

    # Same source IDs in a different namespace and changed row contents are skipped, not updated.
    changed_bundle_path = tmp_path / "changed.zip"
    _write_bundle(
        changed_bundle_path,
        source_system="fake-export-two",
        users=[[rider[0], "rider", "Changed Rider"], [driver[0], "driver", "Changed Driver"]],
        profiles=[_profile(rider[0], total_trips="99"), _profile(driver[0], total_trips="99")],
        trips=[_trip("fake-trip-1", rider[0], driver[0], "Changed Pickup")],
        gps=[["fake-trip-1", "", "2026-09-13T08:43:00+08:00", "1.2847", "103.8382", "99", "changed"]],
        chats=[["fake-trip-1", "", "2026-09-13T08:43:30+08:00", "driver", "message", "Changed content"]],
        events=[["fake-trip-1", "", "2026-09-13T08:44:00+08:00", "changed", "Changed event"]],
    )
    changed = import_bundle(isolated_company_import_database, load_bundle(changed_bundle_path))
    changed_ids = _mapping(changed)
    assert changed.imported_user_count == 0
    assert changed.imported_trip_count == 0
    assert set(changed.skipped_user_ids) == {rider[0], driver[0]}
    assert changed.skipped_trip_ids == ("fake-trip-1",)
    assert changed_ids == first_ids

    with psycopg.connect(isolated_company_import_database) as conn:
        assert conn.execute("SELECT full_name FROM ride_data.users WHERE user_id = %s", (rider_id,)).fetchone()[0] == "Fake Rider"
        assert conn.execute("SELECT total_trips FROM ride_data.user_profiles WHERE user_id = %s", (rider_id,)).fetchone()[0] == 4
        assert conn.execute("SELECT pickup_label FROM ride_data.ride_route_plans WHERE ride_id = %s", (ride_id,)).fetchone()[0] == "Fake Pickup"
        assert conn.execute("SELECT message_text FROM ride_data.ride_chat_messages WHERE ride_id = %s", (ride_id,)).fetchone()[0] == "Synthetic call record"
        assert str(conn.execute("SELECT speed_kmh FROM ride_data.ride_gps_samples WHERE ride_id = %s", (ride_id,)).fetchone()[0]) == "12.5"
        assert conn.execute("SELECT details FROM ride_data.ride_app_events WHERE ride_id = %s", (ride_id,)).fetchone()[0] == "Synthetic event"
        assert conn.execute("SELECT count(*) FROM ride_data.ride_gps_samples WHERE ride_id = %s", (ride_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM ride_data.ride_chat_messages WHERE ride_id = %s", (ride_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM ride_data.ride_app_events WHERE ride_id = %s", (ride_id,)).fetchone()[0] == 1

    # A new trip can refer to a company user that was imported under another source namespace.
    linked_bundle_path = tmp_path / "linked.zip"
    new_driver = ["fake-user-driver-2", "driver", "Fake Driver Two"]
    _write_bundle(
        linked_bundle_path,
        source_system="fake-export-three",
        users=[[rider[0], "rider", "Changed Rider Again"], new_driver],
        profiles=[_profile(rider[0], total_trips="101"), _profile(new_driver[0])],
        trips=[_trip("fake-trip-2", rider[0], new_driver[0], "Second Fake Pickup")],
    )
    linked = import_bundle(isolated_company_import_database, load_bundle(linked_bundle_path))
    linked_ids = _mapping(linked)
    assert linked.imported_user_count == 1
    assert linked.imported_trip_count == 1
    assert linked.skipped_user_ids == (rider[0],)
    assert linked.skipped_trip_ids == ()
    assert linked_ids[("user", rider[0])] == rider_id

    linked_ride_id = linked_ids[("trip", "fake-trip-2")]
    with psycopg.connect(isolated_company_import_database) as conn:
        linked_ride = conn.execute(
            "SELECT rider_user_id, driver_user_id FROM ride_data.rides WHERE ride_id = %s",
            (linked_ride_id,),
        ).fetchone()
        assert linked_ride[0] == rider_id
        assert linked_ride[1] == linked_ids[("user", new_driver[0])]
        assert conn.execute("SELECT full_name FROM ride_data.users WHERE user_id = %s", (rider_id,)).fetchone()[0] == "Fake Rider"
