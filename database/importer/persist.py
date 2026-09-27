"""Append company-export rows to the local queryable database."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .bundle import ImportBundle
from .mapping import render_id_mapping


class ImportDataError(ValueError):
    """Raised when a validated CSV bundle contains a value that cannot be stored."""


def existing_source_id_policy(
    *,
    record_type: str,
    source_system: str,
    company_source_id: str,
    existing_internal_id: str,
    existing_sha256: str,
    incoming_sha256: str,
) -> str:
    """Existing company IDs are skipped, regardless of namespace or changed content."""
    return existing_internal_id


@dataclass(frozen=True)
class ImportResult:
    mapping_csv: str
    imported_user_count: int
    imported_trip_count: int
    skipped_user_ids: tuple[str, ...]
    skipped_trip_ids: tuple[str, ...]


def _sha256(value: object) -> str:
    packed = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def _integer(value: str, field: str, *, required: bool = False) -> int | None:
    if not value:
        if required:
            raise ImportDataError(f"{field} is required")
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ImportDataError(f"{field} must be an integer") from exc
    if parsed < 0:
        raise ImportDataError(f"{field} must be non-negative")
    return parsed


def _decimal(value: str, field: str, *, required: bool = False) -> Decimal | None:
    if not value:
        if required:
            raise ImportDataError(f"{field} is required")
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ImportDataError(f"{field} must be numeric") from exc
    if not parsed.is_finite():
        raise ImportDataError(f"{field} must be finite")
    return parsed


def _timestamp(value: str, field: str, *, required: bool = False) -> datetime | None:
    if not value:
        if required:
            raise ImportDataError(f"{field} is required")
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ImportDataError(f"{field} must be an ISO 8601 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ImportDataError(f"{field} must include a UTC offset")
    return result


def _coordinates(row: Mapping[str, str], lat_key: str, lon_key: str, label: str) -> tuple[Decimal, Decimal]:
    lat = _decimal(row[lat_key], f"{label}.{lat_key}", required=True)
    lon = _decimal(row[lon_key], f"{label}.{lon_key}", required=True)
    assert lat is not None and lon is not None
    if not Decimal(-90) <= lat <= Decimal(90):
        raise ImportDataError(f"{label}.{lat_key} must be between -90 and 90")
    if not Decimal(-180) <= lon <= Decimal(180):
        raise ImportDataError(f"{label}.{lon_key} must be between -180 and 180")
    return lat, lon


def _money_cents(value: str, field: str) -> int | None:
    amount = _decimal(value, field)
    if amount is None:
        return None
    if amount < 0 or amount.as_tuple().exponent < -2:
        raise ImportDataError(f"{field} must be a non-negative amount with at most two decimal places")
    return int(amount * 100)


def _metadata(bundle: ImportBundle) -> dict[tuple[str, str, str, str], Mapping[str, str]]:
    return {
        (
            row["record_type"], row["company_trip_id"], row["company_user_id"], row["sequence_no"],
        ): row
        for row in bundle.tables.get("evidence_metadata.csv", ())
    }


def _evidence_values(
    metadata: Mapping[tuple[str, str, str, str], Mapping[str, str]],
    *,
    record_type: str,
    source_system: str,
    source_file: str,
    company_trip_id: str = "",
    company_user_id: str = "",
    sequence_no: str = "",
    source_sequence_no: str = "",
) -> tuple[str, str | None, str | None, datetime | None, dict[str, Any]]:
    key = (record_type, company_trip_id, company_user_id, sequence_no)
    row = metadata.get(key)
    status = (row or {}).get("verification_status", "") or "unverified"
    evidence_source = (row or {}).get("evidence_source", "") or None
    verified_by = (row or {}).get("verified_by", "") or None
    verified_at = _timestamp((row or {}).get("verified_at", ""), "verified_at")
    provenance: dict[str, Any] = {
        "source_system": source_system,
        "source_file": source_file,
    }
    if company_trip_id:
        provenance["company_trip_id"] = company_trip_id
    if company_user_id:
        provenance["company_user_id"] = company_user_id
    if sequence_no != "":
        provenance["sequence_no"] = int(sequence_no)
        provenance["sequence_no_origin"] = "csv_row_order"
    if source_sequence_no != "":
        provenance["source_sequence_no"] = source_sequence_no
    return status, evidence_source, verified_by, verified_at, provenance


def _validate_values(bundle: ImportBundle) -> None:
    users_by_id = {row["company_user_id"]: row for row in bundle.tables["users.csv"]}
    profiles_by_id = {row["company_user_id"]: row for row in bundle.tables["profiles.csv"]}
    if set(users_by_id) != set(profiles_by_id):
        raise ImportDataError("every user must have exactly one profiles.csv row")
    for profile in profiles_by_id.values():
        _integer(profile["account_age_days"], "account_age_days", required=True)
        _integer(profile["total_trips"], "total_trips")
        rating = _decimal(profile["avg_rating"], "avg_rating", required=True)
        assert rating is not None
        if not Decimal(1) <= rating <= Decimal(5):
            raise ImportDataError("avg_rating must be between 1 and 5")
        for field in (
            "dispute_history_total", "dispute_history_upheld", "dispute_history_rejected",
            "dispute_history_upheld_against", "fraud_flags",
        ):
            _integer(profile[field], field)
    for trip in bundle.tables["trips.csv"]:
        _coordinates(trip, "pickup_lat", "pickup_lng", "trip")
        _coordinates(trip, "dropoff_lat", "dropoff_lng", "trip")
        for field in ("scheduled_time", "driver_arrival_time", "driver_wait_start", "cancellation_time"):
            _timestamp(trip[field], field)
        _money_cents(trip["cancellation_fee"], "cancellation_fee")
        if trip["service_tier"] and trip["service_tier"] not in {"standard", "premium", "assist"}:
            raise ImportDataError("trips.csv service_tier is unsupported")
        for field in ("quoted_distance_meters", "quoted_duration_seconds", "quoted_fare_cents"):
            _integer(trip[field], field)
        for field in ("fare_breakdown_json", "pricing_structure"):
            if trip[field]:
                try:
                    value = json.loads(trip[field])
                except json.JSONDecodeError as exc:
                    raise ImportDataError(f"trips.csv {field} must be valid JSON") from exc
                if not isinstance(value, dict):
                    raise ImportDataError(f"trips.csv {field} must contain a JSON object")
    for rating in bundle.tables.get("ratings.csv", ()):
        value = _decimal(rating["rating"], "ratings.rating", required=True)
        if value is None or not Decimal(1) <= value <= Decimal(5):
            raise ImportDataError("ratings.rating must be between 1 and 5")
        _timestamp(rating["rated_at"], "ratings.rated_at", required=True)
    for row in bundle.tables["gps_telemetry.csv"]:
        _coordinates(row, "lat", "lng", "gps_telemetry")
        _timestamp(row["timestamp"], "gps_telemetry.timestamp", required=True)
        _integer(row["sequence_no"], "gps_telemetry.sequence_no")
        speed = _decimal(row["speed_kmh"], "gps_telemetry.speed_kmh")
        if speed is not None and speed < 0:
            raise ImportDataError("gps_telemetry.speed_kmh must be non-negative")
    for filename in ("chat_logs.csv", "app_events.csv"):
        for row in bundle.tables[filename]:
            _timestamp(row["timestamp"], f"{filename}.timestamp", required=True)
            _integer(row["sequence_no"], f"{filename}.sequence_no")
            if filename == "chat_logs.csv" and row["sender"] not in {"rider", "driver", "support", "system"}:
                raise ImportDataError("chat_logs.sender must be rider, driver, support, or system")


def _next_internal_id(conn: psycopg.Connection[Any], sequence: str, prefix: str) -> str:
    value = conn.execute(
        f"SELECT nextval('ride_data.{sequence}') AS generated_id"
    ).fetchone()["generated_id"]
    if value > 999999:
        raise ImportDataError(f"internal ID range for {prefix} is exhausted")
    return f"{prefix}-{value:06d}"


def _existing_id(
    conn: psycopg.Connection[Any],
    *,
    table: str,
    id_field: str,
    record_type: str,
    source_system: str,
    company_source_id: str,
    incoming_hash: str,
) -> str | None:
    source_id_column = "company_user_id" if record_type == "user" else "company_trip_id"
    rows = conn.execute(
        f"SELECT {id_field}, source_system, {source_id_column}, content_sha256 "
        f"FROM ride_data.{table} WHERE {source_id_column} = %s ORDER BY source_system LIMIT 2",
        (company_source_id,),
    ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        raise ImportDataError(
            f"company {record_type} ID {company_source_id!r} already has multiple database mappings"
        )
    row = rows[0]
    return existing_source_id_policy(
        record_type=record_type,
        source_system=source_system,
        company_source_id=company_source_id,
        existing_internal_id=row[id_field],
        existing_sha256=row["content_sha256"].strip(),
        incoming_sha256=incoming_hash,
    )


def import_bundle(database_url: str, bundle: ImportBundle) -> ImportResult:
    """Append new company IDs atomically; duplicates reuse existing internal IDs."""
    _validate_values(bundle)
    source_system = str(bundle.manifest["source_system"])
    synthetic_data = bundle.manifest.get("synthetic", False) is True
    metadata = _metadata(bundle)
    users = {row["company_user_id"]: row for row in bundle.tables["users.csv"]}
    profiles = {row["company_user_id"]: row for row in bundle.tables["profiles.csv"]}
    trips = {row["company_trip_id"]: row for row in bundle.tables["trips.csv"]}
    gps_by_trip: dict[str, list[Mapping[str, str]]] = {key: [] for key in trips}
    chat_by_trip: dict[str, list[Mapping[str, str]]] = {key: [] for key in trips}
    events_by_trip: dict[str, list[Mapping[str, str]]] = {key: [] for key in trips}
    ratings_by_trip: dict[str, list[Mapping[str, str]]] = {key: [] for key in trips}
    for row in bundle.tables["gps_telemetry.csv"]:
        gps_by_trip[row["company_trip_id"]].append(row)
    for row in bundle.tables["chat_logs.csv"]:
        chat_by_trip[row["company_trip_id"]].append(row)
    for row in bundle.tables["app_events.csv"]:
        events_by_trip[row["company_trip_id"]].append(row)
    for row in bundle.tables.get("ratings.csv", ()):
        ratings_by_trip[row["company_trip_id"]].append(row)

    user_hashes = {
        source_id: _sha256({
            "user": users[source_id], "profile": profiles[source_id],
            "profile_metadata": metadata.get(("profile", "", source_id, "")),
        })
        for source_id in users
    }
    row_metadata_by_trip = {
        source_id: {
            kind: metadata.get((kind, source_id, "", ""))
            for kind in ("trip", "route", "fare")
        }
        | {
            "gps_telemetry": [metadata.get(("gps_telemetry", source_id, "", str(index))) for index, _ in enumerate(gps_by_trip[source_id])],
            "chat_log": [metadata.get(("chat_log", source_id, "", str(index))) for index, _ in enumerate(chat_by_trip[source_id])],
            "app_event": [metadata.get(("app_event", source_id, "", str(index))) for index, _ in enumerate(events_by_trip[source_id])],
        }
        for source_id in trips
    }
    trip_hashes = {
        source_id: _sha256({
            "trip": trips[source_id],
            "gps": gps_by_trip[source_id],
            "chat": chat_by_trip[source_id],
            "events": events_by_trip[source_id],
            "ratings": ratings_by_trip[source_id],
            "evidence_metadata": row_metadata_by_trip[source_id],
        })
        for source_id in trips
    }
    user_ids: dict[str, str] = {}
    trip_ids: dict[str, str] = {}
    skipped_user_ids: set[str] = set()
    skipped_trip_ids: set[str] = set()

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(724931205)")
            # All importer calls serialize through this transaction-scoped advisory lock.
            # Explicit SHARE ROW EXCLUSIVE table locks would require UPDATE/DELETE/TRUNCATE
            # privileges on every locked table, which are broader than an append-only importer needs.
            for source_id, payload_hash in user_hashes.items():
                existing = _existing_id(
                    conn, table="external_user_ids", id_field="user_id", record_type="user",
                    source_system=source_system, company_source_id=source_id,
                    incoming_hash=payload_hash,
                )
                if existing is not None:
                    stored_role = conn.execute(
                        "SELECT role FROM ride_data.users WHERE user_id = %s", (existing,)
                    ).fetchone()["role"]
                    if stored_role != users[source_id]["role"]:
                        raise ImportDataError(
                            f"company user ID {source_id!r} has a different role in the database"
                        )
                    user_ids[source_id] = existing
                    skipped_user_ids.add(source_id)
            for source_id, payload_hash in trip_hashes.items():
                existing = _existing_id(
                    conn, table="external_trip_ids", id_field="ride_id", record_type="trip",
                    source_system=source_system, company_source_id=source_id,
                    incoming_hash=payload_hash,
                )
                if existing is not None:
                    trip_ids[source_id] = existing
                    skipped_trip_ids.add(source_id)

            for source_id, row in users.items():
                if source_id in user_ids:
                    continue
                prefix = "USR-R" if row["role"] == "rider" else "USR-D"
                sequence = "imported_rider_id_seq" if row["role"] == "rider" else "imported_driver_id_seq"
                user_id = _next_internal_id(conn, sequence, prefix)
                user_ids[source_id] = user_id
                status, source, verified_by, verified_at, provenance = _evidence_values(
                    metadata, record_type="profile", source_system=source_system,
                    source_file="profiles.csv", company_user_id=source_id,
                )
                profile = profiles[source_id]
                conn.execute(
                    """
                    INSERT INTO ride_data.users
                      (user_id, role, display_handle, full_name, created_at, account_status, synthetic)
                    VALUES (%s, %s, NULL, %s, NULL, NULL, %s)
                    """,
                    (user_id, row["role"], row["name"] or None, synthetic_data),
                )
                conn.execute(
                    """
                    INSERT INTO ride_data.user_profiles
                      (user_id, account_age_days, lifetime_completed_rides, average_rating, rating_trend,
                       synthetic, total_trips, dispute_history_total, dispute_history_upheld,
                       dispute_history_rejected, dispute_history_upheld_against, fraud_flag_count,
                       fraud_flag_details, payment_method, vehicle, evidence_source,
                       verification_status, verified_by, verified_at, provenance)
                    VALUES (%s,%s,NULL,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        user_id,
                        _integer(profile["account_age_days"], "account_age_days", required=True),
                        _decimal(profile["avg_rating"], "avg_rating", required=True),
                        synthetic_data,
                        _integer(profile["total_trips"], "total_trips"),
                        _integer(profile["dispute_history_total"], "dispute_history_total"),
                        _integer(profile["dispute_history_upheld"], "dispute_history_upheld"),
                        _integer(profile["dispute_history_rejected"], "dispute_history_rejected"),
                        _integer(profile["dispute_history_upheld_against"], "dispute_history_upheld_against"),
                        _integer(profile["fraud_flags"], "fraud_flags"), profile["fraud_flag_details"] or None,
                        profile["payment_method"] or None, profile["vehicle"] or None,
                        source, status, verified_by, verified_at, Jsonb(provenance),
                    ),
                )
                conn.execute(
                    "INSERT INTO ride_data.user_dispute_counters "
                    "(user_id, disputes_30d, disputes_180d, route_deviation_count, no_show_count, "
                    "property_damage_count, safety_incident_count, synthetic) "
                    "VALUES (%s,NULL,NULL,NULL,NULL,NULL,NULL,%s)",
                    (user_id, synthetic_data),
                )
                conn.execute(
                    "INSERT INTO ride_data.external_user_ids "
                    "(source_system, company_user_id, user_id, content_sha256) VALUES (%s,%s,%s,%s)",
                    (source_system, source_id, user_id, user_hashes[source_id]),
                )

            for source_id, row in trips.items():
                if source_id in trip_ids:
                    continue
                ride_id = _next_internal_id(conn, "imported_ride_id_seq", "RIDE")
                trip_ids[source_id] = ride_id
                rider_id = user_ids[row["company_rider_id"]]
                driver_id = user_ids[row["company_driver_id"]]
                scheduled_at = _timestamp(row["scheduled_time"], "scheduled_time")
                arrival_at = _timestamp(row["driver_arrival_time"], "driver_arrival_time")
                wait_start = _timestamp(row["driver_wait_start"], "driver_wait_start")
                cancellation_at = _timestamp(row["cancellation_time"], "cancellation_time")
                fee_cents = _money_cents(row["cancellation_fee"], "cancellation_fee")
                fare_breakdown = json.loads(row["fare_breakdown_json"]) if row["fare_breakdown_json"] else {}
                fare_text = {key: "" if value is None else str(value) for key, value in fare_breakdown.items()}
                if row["pricing_structure"]:
                    trip_provenance["pricing_structure"] = json.loads(row["pricing_structure"])
                pickup_lat, pickup_lon = _coordinates(row, "pickup_lat", "pickup_lng", "trip")
                dropoff_lat, dropoff_lon = _coordinates(row, "dropoff_lat", "dropoff_lng", "trip")
                trip_status, trip_source, trip_verifier, trip_verified_at, trip_provenance = _evidence_values(
                    metadata, record_type="trip", source_system=source_system,
                    source_file="trips.csv", company_trip_id=source_id,
                )
                route_status, route_source, route_verifier, route_verified_at, route_provenance = _evidence_values(
                    metadata, record_type="route", source_system=source_system,
                    source_file="trips.csv", company_trip_id=source_id,
                )
                fare_status, fare_source, fare_verifier, fare_verified_at, fare_provenance = _evidence_values(
                    metadata, record_type="fare", source_system=source_system,
                    source_file="trips.csv", company_trip_id=source_id,
                )
                conn.execute(
                    """
                    INSERT INTO ride_data.rides
                      (ride_id, rider_user_id, driver_user_id, requested_at, scheduled_at,
                       accepted_at, pickup_at, dropoff_at, cancellation_at, cancellation_reason,
                       ride_status, service_tier, quoted_distance_meters, quoted_duration_seconds,
                       quoted_fare_cents, currency, synthetic, evidence_source,
                       verification_status, verified_by, verified_at, provenance)
                    VALUES (%s,%s,%s,NULL,%s,NULL,NULL,NULL,%s,%s,%s,%s,%s,%s,%s,%s,
                       %s,%s,%s,%s,%s,%s)
                    """,
                    (ride_id, rider_id, driver_id, scheduled_at, cancellation_at,
                     row["cancellation_reason"] or None, row["ride_status"] or None,
                     row["service_tier"] or None,
                     _integer(row["quoted_distance_meters"], "quoted_distance_meters"),
                     _integer(row["quoted_duration_seconds"], "quoted_duration_seconds"),
                     _integer(row["quoted_fare_cents"], "quoted_fare_cents"),
                     str(fare_breakdown.get("currency") or "SGD"), synthetic_data, trip_source, trip_status,
                     trip_verifier, trip_verified_at, Jsonb(trip_provenance)),
                )
                conn.execute(
                    """
                    INSERT INTO ride_data.external_trip_ids
                      (source_system, company_trip_id, ride_id, content_sha256)
                    VALUES (%s,%s,%s,%s)
                    """,
                    (source_system, source_id, ride_id, trip_hashes[source_id]),
                )
                conn.execute(
                    """
                    INSERT INTO ride_data.ride_route_plans
                      (ride_id, pickup_label, pickup_lat, pickup_lon, dropoff_label, dropoff_lat,
                       dropoff_lon, planned_distance_meters, actual_distance_meters,
                       planned_duration_seconds, actual_duration_seconds, driver_arrival_distance_meters,
                       driver_wait_seconds, driver_arrival_at, driver_wait_start_at, synthetic,
                       evidence_source, verification_status, verified_by, verified_at, provenance)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,NULL,NULL,NULL,NULL,NULL,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (ride_id, row["pickup_location_name"], pickup_lat, pickup_lon,
                     row["dropoff_location_name"], dropoff_lat, dropoff_lon, arrival_at, wait_start,
                     synthetic_data, route_source, route_status, route_verifier, route_verified_at, Jsonb(route_provenance)),
                )
                conn.execute(
                    """
                    INSERT INTO ride_data.ride_fare_breakdowns
                      (ride_id, base_fare_cents, distance_fare_cents, time_fare_cents,
                       waiting_fare_cents, surge_multiplier, surge_fare_cents,
                       cancellation_fee_cents, platform_fee_cents, total_fare_cents,
                       currency, synthetic, evidence_source, verification_status,
                       verified_by, verified_at, provenance)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (ride_id,
                     _integer(fare_text.get("base_fare_cents", ""), "base_fare_cents"),
                     _integer(fare_text.get("distance_fare_cents", ""), "distance_fare_cents"),
                     _integer(fare_text.get("time_fare_cents", ""), "time_fare_cents"),
                     _integer(fare_text.get("waiting_fare_cents", ""), "waiting_fare_cents"),
                     _decimal(fare_text.get("surge_multiplier", ""), "surge_multiplier"),
                     _integer(fare_text.get("surge_fare_cents", ""), "surge_fare_cents"),
                     fee_cents,
                     _integer(fare_text.get("platform_fee_cents", ""), "platform_fee_cents"),
                     _integer(fare_text.get("total_fare_cents", ""), "total_fare_cents"),
                     str(fare_breakdown.get("currency") or "SGD"), synthetic_data, fare_source, fare_status, fare_verifier,
                     fare_verified_at, Jsonb(fare_provenance)),
                )

                for sequence_no, gps in enumerate(gps_by_trip[source_id]):
                    status, evidence_source, verifier, verified_at, provenance = _evidence_values(
                        metadata, record_type="gps_telemetry", source_system=source_system,
                        source_file="gps_telemetry.csv", company_trip_id=source_id,
                        sequence_no=str(sequence_no), source_sequence_no=gps["sequence_no"],
                    )
                    lat, lon = _coordinates(gps, "lat", "lng", "gps_telemetry")
                    speed_kmh = _decimal(gps["speed_kmh"], "gps_telemetry.speed_kmh")
                    speed_mps = speed_kmh / Decimal("3.6") if speed_kmh is not None else None
                    conn.execute(
                        """
                        INSERT INTO ride_data.ride_gps_samples
                          (ride_id, sample_at, sequence_no, lat, lon, accuracy_meters,
                           speed_meters_per_second, speed_kmh, status, collector, source_system,
                           evidence_source, verification_status, verified_by, verified_at,
                           provenance, synthetic)
                        VALUES (%s,%s,%s,%s,%s,NULL,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (ride_id, _timestamp(gps["timestamp"], "gps_telemetry.timestamp", required=True),
                         sequence_no, lat, lon, speed_mps, speed_kmh, gps["status"] or None,
                         source_system, evidence_source, status, verifier, verified_at, Jsonb(provenance), synthetic_data),
                    )
                for sequence_no, message in enumerate(chat_by_trip[source_id]):
                    message_id = _next_internal_id(conn, "imported_evidence_id_seq", "EV")
                    status, evidence_source, verifier, verified_at, provenance = _evidence_values(
                        metadata, record_type="chat_log", source_system=source_system,
                        source_file="chat_logs.csv", company_trip_id=source_id,
                        sequence_no=str(sequence_no), source_sequence_no=message["sequence_no"],
                    )
                    conn.execute(
                        """
                        INSERT INTO ride_data.ride_chat_messages
                          (message_id, ride_id, participant_role, sent_at, message_text, sequence_no,
                           message_type, source_system, evidence_source, verification_status,
                           verified_by, verified_at, provenance, synthetic)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (message_id, ride_id, message["sender"],
                         _timestamp(message["timestamp"], "chat_logs.timestamp", required=True),
                         message["content"], sequence_no, message["type"], source_system,
                         evidence_source, status, verifier, verified_at, Jsonb(provenance), synthetic_data),
                    )
                for sequence_no, event in enumerate(events_by_trip[source_id]):
                    event_id = _next_internal_id(conn, "imported_evidence_id_seq", "EV")
                    status, evidence_source, verifier, verified_at, provenance = _evidence_values(
                        metadata, record_type="app_event", source_system=source_system,
                        source_file="app_events.csv", company_trip_id=source_id,
                        sequence_no=str(sequence_no), source_sequence_no=event["sequence_no"],
                    )
                    conn.execute(
                        """
                        INSERT INTO ride_data.ride_app_events
                          (event_id, ride_id, sequence_no, event_at, event_type, details, source_system,
                           evidence_source, verification_status, verified_by, verified_at,
                           provenance, synthetic)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (event_id, ride_id, sequence_no,
                         _timestamp(event["timestamp"], "app_events.timestamp", required=True),
                         event["event_type"], event["details"], source_system, evidence_source,
                         status, verifier, verified_at, Jsonb(provenance), synthetic_data),
                    )
                for rating in ratings_by_trip[source_id]:
                    conn.execute(
                        """
                        INSERT INTO ride_data.ride_ratings
                          (ride_id, rated_user_id, rating_from_role, rating, rated_at, synthetic)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        """,
                        (ride_id, user_ids[rating["company_rated_user_id"]], rating["rating_from_role"],
                         _decimal(rating["rating"], "ratings.rating", required=True),
                         _timestamp(rating["rated_at"], "ratings.rated_at", required=True), synthetic_data),
                    )
    skipped_users = tuple(sorted(skipped_user_ids))
    skipped_trips = tuple(sorted(skipped_trip_ids))
    return ImportResult(
        mapping_csv=render_id_mapping(source_system, user_ids, trip_ids),
        imported_user_count=len(users) - len(skipped_users),
        imported_trip_count=len(trips) - len(skipped_trips),
        skipped_user_ids=skipped_users,
        skipped_trip_ids=skipped_trips,
    )
