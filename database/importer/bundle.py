"""Parse and validate the versioned company-export ZIP format.

This module has no database side effects. It validates the complete bundle before a
database importer is allowed to write any rows.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


FORMAT_VERSION = "1"
REQUIRED_CSVS = {
    "users.csv": {
        "company_user_id", "role", "name",
    },
    "profiles.csv": {
        "company_user_id", "account_age_days", "total_trips", "avg_rating",
        "dispute_history_total", "dispute_history_upheld", "dispute_history_rejected",
        "dispute_history_upheld_against", "fraud_flags", "fraud_flag_details",
        "payment_method", "vehicle",
    },
    "trips.csv": {
        "company_trip_id", "company_rider_id", "company_driver_id",
        "pickup_location_name", "pickup_lat", "pickup_lng", "dropoff_location_name",
        "dropoff_lat", "dropoff_lng", "scheduled_time", "driver_arrival_time",
        "driver_wait_start", "cancellation_time", "cancellation_fee", "cancellation_reason",
        "ride_status",
    },
    "gps_telemetry.csv": {
        "company_trip_id", "sequence_no", "timestamp", "lat", "lng", "speed_kmh", "status",
    },
    "chat_logs.csv": {
        "company_trip_id", "sequence_no", "timestamp", "sender", "type", "content",
    },
    "app_events.csv": {
        "company_trip_id", "sequence_no", "timestamp", "event_type", "details",
    },
}
OPTIONAL_CSVS = {
    "evidence_metadata.csv": {
        "record_type", "company_trip_id", "company_user_id", "sequence_no",
        "verification_status", "verified_by", "verified_at", "evidence_source",
    },
    "ratings.csv": {
        "company_trip_id", "company_rated_user_id", "rating_from_role", "rating", "rated_at",
    },
}
OPTIONAL_COLUMNS = {
    "gps_telemetry.csv": {"sequence_no"},
    "chat_logs.csv": {"sequence_no"},
    "app_events.csv": {"sequence_no"},
}
EXPECTED_FILES = {"manifest.json", *REQUIRED_CSVS, *OPTIONAL_CSVS}
OPTIONAL_CSV_COLUMNS = {
    "trips.csv": {
        "ride_status", "service_tier", "quoted_distance_meters", "quoted_duration_seconds",
        "quoted_fare_cents", "fare_breakdown_json", "pricing_structure",
    }
}


class BundleValidationError(ValueError):
    """Raised when an archive is invalid or has unresolved row references."""


@dataclass(frozen=True)
class ImportBundle:
    manifest: Mapping[str, object]
    tables: Mapping[str, tuple[Mapping[str, str], ...]]


def _read_csv(
    raw: bytes,
    filename: str,
    expected_columns: set[str],
    optional_columns: set[str] | None = None,
) -> tuple[Mapping[str, str], ...]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BundleValidationError(f"{filename} must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise BundleValidationError(f"{filename} must have a header row")
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise BundleValidationError(f"{filename} has duplicate column names")
    optional_columns = optional_columns or set()
    missing = (expected_columns - optional_columns) - set(reader.fieldnames)
    extra = set(reader.fieldnames) - expected_columns - optional_columns
    if missing or extra:
        details = []
        if missing:
            details.append("missing: " + ", ".join(sorted(missing)))
        if extra:
            details.append("unexpected: " + ", ".join(sorted(extra)))
        raise BundleValidationError(f"{filename} columns invalid ({'; '.join(details)})")
    rows: list[Mapping[str, str]] = []
    for row_number, row in enumerate(reader, start=2):
        if None in row:
            raise BundleValidationError(f"{filename}:{row_number} has more values than columns")
        # Keep original strings exactly; conversion belongs to the DB insertion layer.
        normalized = {key: value if value is not None else "" for key, value in row.items()}
        for key in optional_columns - set(reader.fieldnames):
            normalized[key] = ""
        rows.append(normalized)
    return tuple(rows)


def load_bundle(path: str | Path) -> ImportBundle:
    """Load a CSV ZIP, requiring the full v1 file set and rejecting unsafe paths."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BundleValidationError("input must be a readable ZIP archive") from exc
    with archive:
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(names) != len(set(names)):
            raise BundleValidationError("ZIP contains duplicate file names")
        if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
            raise BundleValidationError("ZIP contains an unsafe file path")
        actual = set(names)
        missing = {"manifest.json", *REQUIRED_CSVS} - actual
        unexpected = actual - EXPECTED_FILES
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing: " + ", ".join(sorted(missing)))
            if unexpected:
                details.append("unexpected: " + ", ".join(sorted(unexpected)))
            raise BundleValidationError("ZIP members invalid (" + "; ".join(details) + ")")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleValidationError("manifest.json must contain valid UTF-8 JSON") from exc
        if not isinstance(manifest, dict) or manifest.get("format_version") != FORMAT_VERSION:
            raise BundleValidationError(f"manifest format_version must be {FORMAT_VERSION!r}")
        if not isinstance(manifest.get("source_system"), str) or not manifest["source_system"].strip():
            raise BundleValidationError("manifest source_system must be a non-empty stable namespace")
        if "synthetic" in manifest and not isinstance(manifest["synthetic"], bool):
            raise BundleValidationError("manifest synthetic must be a boolean when supplied")
        if "dispute_ticket" in manifest or any(Path(name).name == "dispute_ticket.csv" for name in names):
            raise BundleValidationError("dispute tickets are filed separately and cannot be imported")

        tables = {}
        for filename, columns in REQUIRED_CSVS.items():
            tables[filename] = _read_csv(
                archive.read(filename), filename, columns,
                OPTIONAL_COLUMNS.get(filename, set()) | OPTIONAL_CSV_COLUMNS.get(filename, set()),
            )
        for filename, columns in OPTIONAL_CSVS.items():
            if filename in actual:
                tables[filename] = _read_csv(archive.read(filename), filename, columns)

    _validate_references(tables)
    return ImportBundle(manifest=manifest, tables=tables)


def _validate_references(tables: Mapping[str, tuple[Mapping[str, str], ...]]) -> None:
    user_rows = tables["users.csv"]
    user_ids = [row["company_user_id"] for row in user_rows]
    trip_ids = [row["company_trip_id"] for row in tables["trips.csv"]]
    if any(not value.strip() for value in user_ids):
        raise BundleValidationError("users.csv company_user_id must not be blank")
    if any(not value.strip() for value in trip_ids):
        raise BundleValidationError("trips.csv company_trip_id must not be blank")
    if len(user_ids) != len(set(user_ids)):
        raise BundleValidationError("users.csv contains duplicate company_user_id values")
    if len(trip_ids) != len(set(trip_ids)):
        raise BundleValidationError("trips.csv contains duplicate company_trip_id values")
    profile_ids = [row["company_user_id"] for row in tables["profiles.csv"]]
    if len(profile_ids) != len(set(profile_ids)):
        raise BundleValidationError("profiles.csv contains duplicate company_user_id values")
    known_users = set(user_ids)
    known_trips = set(trip_ids)
    user_roles = {row["company_user_id"]: row["role"] for row in user_rows}
    if any(role not in {"rider", "driver"} for role in user_roles.values()):
        raise BundleValidationError("users.csv role must be rider or driver")
    for row in tables["trips.csv"]:
        if row["company_rider_id"] not in known_users or row["company_driver_id"] not in known_users:
            raise BundleValidationError(
                f"trip {row['company_trip_id']!r} references a user absent from users.csv"
            )
        if user_roles[row["company_rider_id"]] != "rider":
            raise BundleValidationError(
                f"trip {row['company_trip_id']!r} company_rider_id must reference a rider"
            )
        if user_roles[row["company_driver_id"]] != "driver":
            raise BundleValidationError(
                f"trip {row['company_trip_id']!r} company_driver_id must reference a driver"
            )
        if row["ride_status"] and row["ride_status"] not in {
            "completed", "cancelled_after_arrival", "cancelled_before_assignment",
        }:
            raise BundleValidationError("trips.csv ride_status is unsupported")
    if "ratings.csv" in tables:
        if any(not row["ride_status"] for row in tables["trips.csv"]):
            raise BundleValidationError("trips.csv ride_status is required when ratings.csv is present")
        seen_rating_keys = set()
        by_trip: dict[str, list[Mapping[str, str]]] = {}
        rating_totals: dict[str, list[float]] = {}
        trip_by_id = {row["company_trip_id"]: row for row in tables["trips.csv"]}
        for rating_row in tables["ratings.csv"]:
            trip_id = rating_row["company_trip_id"]
            user_id = rating_row["company_rated_user_id"]
            rater_role = rating_row["rating_from_role"]
            if trip_id not in known_trips or user_id not in known_users:
                raise BundleValidationError("ratings.csv references an unknown trip or user")
            if rater_role not in {"rider", "driver"}:
                raise BundleValidationError("ratings.csv rating_from_role must be rider or driver")
            trip = trip_by_id[trip_id]
            if user_id not in {trip["company_rider_id"], trip["company_driver_id"]}:
                raise BundleValidationError("ratings.csv rated user must be a trip participant")
            if user_roles[user_id] == rater_role:
                raise BundleValidationError("rating must come from the other trip participant")
            key = (trip_id, user_id)
            if key in seen_rating_keys:
                raise BundleValidationError("ratings.csv duplicates a trip and rated-user pair")
            seen_rating_keys.add(key)
            try:
                value = float(rating_row["rating"])
            except ValueError as exc:
                raise BundleValidationError("ratings.csv rating must be numeric") from exc
            if not 1 <= value <= 5 or not rating_row["rated_at"].strip():
                raise BundleValidationError("ratings.csv rating must be from 1 to 5 and include rated_at")
            by_trip.setdefault(trip_id, []).append(rating_row)
            rating_totals.setdefault(user_id, []).append(value)
        for trip_id, trip in trip_by_id.items():
            rows = by_trip.get(trip_id, [])
            if trip["ride_status"] == "completed" and len(rows) != 2:
                raise BundleValidationError(f"completed trip {trip_id!r} must have exactly two ratings")
            if trip["ride_status"] and trip["ride_status"] != "completed" and rows:
                raise BundleValidationError(f"cancelled trip {trip_id!r} must not have ratings")
        profile_by_id = {row["company_user_id"]: row for row in tables["profiles.csv"]}
        if set(rating_totals) != set(profile_by_id):
            raise BundleValidationError("ratings.csv must contain received ratings for every user profile")
        for user_id, values in rating_totals.items():
            profile_average = float(profile_by_id[user_id]["avg_rating"])
            if round(sum(values) / len(values) + 1e-9, 2) != round(profile_average + 1e-9, 2):
                raise BundleValidationError(
                    f"profiles.csv avg_rating for {user_id!r} must equal their average received trip rating"
                )
    for filename in ("profiles.csv",):
        if filename in tables:
            for row in tables[filename]:
                if row["company_user_id"] not in known_users:
                    raise BundleValidationError(
                        f"{filename} references user {row['company_user_id']!r} absent from users.csv"
                    )
    row_orders: dict[str, dict[tuple[str, str], int]] = {}
    for filename in ("gps_telemetry.csv", "chat_logs.csv", "app_events.csv"):
        next_order: dict[str, int] = {}
        orders: dict[tuple[str, str], int] = {}
        for row in tables.get(filename, ()):
            if row["company_trip_id"] not in known_trips:
                raise BundleValidationError(
                    f"{filename} references trip {row['company_trip_id']!r} absent from trips.csv"
                )
            source_sequence = row["sequence_no"]
            if source_sequence and (not source_sequence.isdecimal()):
                raise BundleValidationError(f"{filename}.sequence_no must be a non-negative integer or blank")
            trip_id = row["company_trip_id"]
            order = next_order.get(trip_id, 0)
            orders[(trip_id, str(order))] = order
            next_order[trip_id] = order + 1
        row_orders[filename] = orders
    if "evidence_metadata.csv" in tables:
        evidence_keys = {
            ("trip", row["company_trip_id"], "", "") for row in tables["trips.csv"]
        }
        evidence_keys.update(
            ("route", row["company_trip_id"], "", "") for row in tables["trips.csv"]
        )
        evidence_keys.update(
            ("fare", row["company_trip_id"], "", "") for row in tables["trips.csv"]
        )
        evidence_keys.update(
            ("profile", "", row["company_user_id"], "") for row in tables["profiles.csv"]
        )
        for filename, record_type in (
            ("gps_telemetry.csv", "gps_telemetry"),
            ("chat_logs.csv", "chat_log"),
            ("app_events.csv", "app_event"),
        ):
            evidence_keys.update(
                (record_type, trip_id, "", sequence)
                for trip_id, sequence in row_orders[filename]
            )
        seen_metadata = set()
        allowed_statuses = {"", "verified", "unverified", "disputed", "unverifiable"}
        for row in tables["evidence_metadata.csv"]:
            kind = row["record_type"]
            trip_id = row["company_trip_id"]
            user_id = row["company_user_id"]
            sequence = row["sequence_no"]
            if row["verification_status"] not in allowed_statuses:
                raise BundleValidationError("evidence_metadata.csv has an unsupported verification_status")
            if kind == "profile":
                if trip_id or sequence or not user_id:
                    raise BundleValidationError("profile metadata must use company_user_id only")
            elif kind in {"trip", "route", "fare"}:
                if not trip_id or user_id or sequence:
                    raise BundleValidationError(f"{kind} metadata must use company_trip_id only")
            elif kind in {"gps_telemetry", "chat_log", "app_event"}:
                if not trip_id or user_id or not sequence:
                    raise BundleValidationError(
                        f"{kind} metadata must use company_trip_id and the zero-based CSV row order"
                    )
            else:
                raise BundleValidationError(f"unsupported evidence record_type {kind!r}")
            key = (kind, trip_id, user_id, sequence)
            if key in seen_metadata:
                raise BundleValidationError("evidence_metadata.csv contains duplicate record keys")
            seen_metadata.add(key)
            if key not in evidence_keys:
                raise BundleValidationError(
                    "evidence_metadata.csv row does not reference a matching evidence record"
                )
