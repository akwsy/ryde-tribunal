"""Parse and validate a ZIP of linked synthetic or historical archive CSVs."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

FORMAT_VERSION = "1"
CSV_COLUMNS = {
    "users.csv": {"source_user_key", "role", "display_name", "account_age_days", "average_rating", "total_trips"},
    "trips.csv": {"source_trip_key", "rider_source_user_key", "driver_source_user_key", "trip_status", "trip_at", "requested_at", "accepted_at", "pickup_at", "dropoff_at", "service_tier", "quoted_distance_meters", "quoted_duration_seconds", "quoted_fare_cents", "fare_cents", "currency", "rider_rating", "driver_rating", "fare_breakdown", "pricing_structure", "pickup_details", "dropoff_details", "gps_data"},
    "cases.csv": {"source_case_key", "source_trip_key", "filing_user_source_key", "category", "subject", "filed_by", "created_at", "policy_version", "primary_classification", "secondary_classifications", "monetary_impact_cents", "fraud_risk"},
    "rulings.csv": {"source_case_key", "stage", "origin", "verdict", "ruling_type", "action_description", "amount_cents", "currency", "confidence", "decided_at"},
    "reviews.csv": {"source_case_key", "reason_code", "rationale", "agreed_with_agent", "changed_fields", "reweighted_evidence", "reviewed_at"},
    "evidence.csv": {"source_evidence_key", "source_case_key", "evidence_class", "source", "recorded_at", "provenance", "verification", "visibility", "payload"},
}
ALLOWED_CATEGORIES = {
    "route_deviation", "no_show_charge", "fare_calculation", "other_cancellation_fee",
    "property_damage", "safety_incident", "lost_item", "conduct_complaint",
}


class ArchiveBundleError(ValueError):
    """Invalid archive import bundle."""


@dataclass(frozen=True)
class ArchiveBundle:
    manifest: Mapping[str, object]
    tables: Mapping[str, tuple[Mapping[str, str], ...]]


def _csv_rows(raw: bytes, filename: str, columns: set[str]) -> tuple[Mapping[str, str], ...]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ArchiveBundleError(f"{filename} must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ArchiveBundleError(f"{filename} must have a unique header row")
    if set(reader.fieldnames) != columns:
        raise ArchiveBundleError(f"{filename} columns must be: {', '.join(sorted(columns))}")
    result = []
    for n, row in enumerate(reader, 2):
        if None in row:
            raise ArchiveBundleError(f"{filename}:{n} has extra values")
        result.append({key: value or "" for key, value in row.items()})
    return tuple(result)


def load_bundle(path: str | Path) -> ArchiveBundle:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveBundleError("input must be a readable ZIP") from exc
    with archive:
        members = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(members) != len(set(members)) or any(Path(n).is_absolute() or ".." in Path(n).parts for n in members):
            raise ArchiveBundleError("ZIP has duplicate names or unsafe paths")
        required = {"manifest.json", *CSV_COLUMNS}
        if set(members) != required:
            raise ArchiveBundleError("ZIP must contain manifest.json and the six related CSV files only")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArchiveBundleError("manifest.json must be valid UTF-8 JSON") from exc
        if not isinstance(manifest, dict) or manifest.get("format_version") != FORMAT_VERSION:
            raise ArchiveBundleError("manifest format_version must be '1'")
        if not isinstance(manifest.get("source_system"), str) or not manifest["source_system"].strip():
            raise ArchiveBundleError("manifest source_system must be non-empty")
        tables = {name: _csv_rows(archive.read(name), name, columns) for name, columns in CSV_COLUMNS.items()}
    _validate(tables)
    return ArchiveBundle(manifest, tables)


def _validate(tables: Mapping[str, tuple[Mapping[str, str], ...]]) -> None:
    users = tables["users.csv"]
    trips = tables["trips.csv"]
    cases = tables["cases.csv"]
    rulings = tables["rulings.csv"]
    user_map = {row["source_user_key"]: row for row in users}
    trip_map = {row["source_trip_key"]: row for row in trips}
    case_map = {row["source_case_key"]: row for row in cases}
    for filename, rows, key in (("users.csv", users, "source_user_key"), ("trips.csv", trips, "source_trip_key"), ("cases.csv", cases, "source_case_key")):
        values = [row[key] for row in rows]
        if any(not v.strip() for v in values) or len(values) != len(set(values)):
            raise ArchiveBundleError(f"{filename} keys must be non-empty and unique")
    for row in users:
        if row["role"] not in {"rider", "driver"} or not row["display_name"]:
            raise ArchiveBundleError("users.csv roles and names are required")
        try:
            if int(row["account_age_days"]) < 0:
                raise ValueError
            if row["average_rating"] and not 1 <= float(row["average_rating"]) <= 5:
                raise ValueError
            if row["total_trips"] and int(row["total_trips"]) < 0:
                raise ValueError
        except ValueError as exc:
            raise ArchiveBundleError("user account age, rating, or trip count is invalid") from exc
    received_ratings: dict[str, list[float]] = {}
    for row in trips:
        rider, driver = user_map.get(row["rider_source_user_key"]), user_map.get(row["driver_source_user_key"])
        if rider is None or driver is None or rider["role"] != "rider" or driver["role"] != "driver":
            raise ArchiveBundleError("each trip must reference one bundle rider and one bundle driver")
        if row["trip_status"] not in {"completed", "cancelled_after_arrival", "cancelled_before_assignment"}:
            raise ArchiveBundleError("trips.csv has an unsupported trip_status")
        try:
            if row["service_tier"] not in {"standard", "premium", "assist"}:
                raise ValueError("unsupported service tier")
            timestamps = [row_time(row[key]) for key in ("requested_at", "trip_at")]
            for key in ("accepted_at", "pickup_at", "dropoff_at"):
                if row[key]:
                    timestamps.append(row_time(row[key]))
            if timestamps != sorted(timestamps):
                raise ValueError("trip timestamps are out of order")
            rider_rating = float(row["rider_rating"]) if row["rider_rating"] else None
            driver_rating = float(row["driver_rating"]) if row["driver_rating"] else None
            if row["trip_status"] == "completed":
                if rider_rating is None or driver_rating is None or not 1 <= rider_rating <= 5 or not 1 <= driver_rating <= 5:
                    raise ValueError("completed archive trip must have two participant ratings")
                # rider_rating is given by the rider and received by the driver; driver_rating
                # is given by the driver and received by the rider. Profiles store ratings received.
                received_ratings.setdefault(row["driver_source_user_key"], []).append(rider_rating)
                received_ratings.setdefault(row["rider_source_user_key"], []).append(driver_rating)
            elif rider_rating is not None or driver_rating is not None:
                raise ValueError("cancelled archive trip cannot have ratings")
            structured = {key: json.loads(row[key]) for key in ("fare_breakdown", "pricing_structure", "pickup_details", "dropoff_details", "gps_data")}
            if any(not isinstance(structured[key], dict) for key in ("fare_breakdown", "pricing_structure", "pickup_details", "dropoff_details")):
                raise ValueError("trip detail fields must contain JSON objects")
            if not isinstance(structured["gps_data"], list):
                raise ValueError("gps_data must contain a JSON list")
            for point in structured["gps_data"]:
                if not isinstance(point, dict):
                    raise ValueError("GPS samples must be JSON objects")
                point_at = point.get("recorded_at", point.get("timestamp"))
                row_time(point_at)
                latitude, longitude = float(point["lat"]), float(point["lon"])
                if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    raise ValueError("GPS coordinates are outside valid ranges")
            if len(row["currency"]) != 3 or min(int(row[k]) for k in ("quoted_distance_meters", "quoted_duration_seconds", "quoted_fare_cents", "fare_cents")) < 0:
                raise ValueError
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ArchiveBundleError("trip fare and JSON detail fields must be valid") from exc
    for key, user in user_map.items():
        values = received_ratings.get(key, [])
        if not values or not user["average_rating"]:
            raise ArchiveBundleError(f"archive user {key!r} must receive at least one trip rating")
        profile_rating = float(user["average_rating"])
        if round(sum(values) / len(values) + 1e-9, 2) != round(profile_rating + 1e-9, 2):
            raise ArchiveBundleError(f"archive user {key!r} average must match received trip ratings")
    for row in cases:
        trip = trip_map.get(row["source_trip_key"])
        filer = user_map.get(row["filing_user_source_key"])
        if trip is None or filer is None or row["category"] not in ALLOWED_CATEGORIES:
            raise ArchiveBundleError("case references a missing trip/user or unsupported category")
        if filer["role"] != row["filed_by"] or row["filed_by"] not in {"rider", "driver"}:
            raise ArchiveBundleError("case filer must match its recorded rider/driver role")
        party_key = trip["rider_source_user_key"] if row["filed_by"] == "rider" else trip["driver_source_user_key"]
        if party_key != row["filing_user_source_key"]:
            raise ArchiveBundleError("case filer must be the rider or driver from its linked trip")
        if not row["subject"].strip() or not row["policy_version"].strip():
            raise ArchiveBundleError("case subject and policy_version are required")
        try:
            trip_at = row_time(trip["trip_at"])
            created_at = row_time(row["created_at"])
            if created_at <= trip_at:
                raise ArchiveBundleError("each dispute must be filed strictly after its trip")
            json.loads(row["secondary_classifications"])
            impact, risk = int(row["monetary_impact_cents"]), float(row["fraud_risk"])
            if impact < 0 or not 0 <= risk <= 1:
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            if isinstance(exc, ArchiveBundleError):
                raise
            raise ArchiveBundleError("case values or timestamps are malformed") from exc
    by_case: dict[str, set[str]] = {}
    stage_counts: dict[tuple[str, str], int] = {}
    for row in rulings:
        if row["source_case_key"] not in case_map:
            raise ArchiveBundleError("rulings.csv references an unknown case")
        stage = row["stage"]
        if (stage, row["origin"]) not in {("model_proposed", "agent"), ("reviewer_approved", "human")}:
            raise ArchiveBundleError("ruling stage and origin are inconsistent")
        if row["verdict"] not in {"refund", "compensation", "no_action", "escalated"}:
            raise ArchiveBundleError("rulings.csv has an unsupported verdict")
        if row["ruling_type"] not in {"refund", "compensation", "no_action"}:
            raise ArchiveBundleError("rulings.csv has an unsupported ruling type")
        by_case.setdefault(row["source_case_key"], set()).add(stage)
        stage_counts[(row["source_case_key"], stage)] = stage_counts.get((row["source_case_key"], stage), 0) + 1
        try:
            amount = int(row["amount_cents"])
            confidence = float(row["confidence"]) if row["confidence"] else None
            row_time(row["decided_at"])
            if amount < 0 or (confidence is not None and not 0 <= confidence <= 1):
                raise ValueError
        except ValueError as exc:
            raise ArchiveBundleError("ruling amount, confidence, or timestamp is invalid") from exc
    if set(by_case) != set(case_map):
        raise ArchiveBundleError("each case must have at least one recorded ruling")
    if any(count > 1 for count in stage_counts.values()):
        raise ArchiveBundleError("a case may have at most one ruling per stage")
    review_map = {row["source_case_key"]: row for row in tables["reviews.csv"]}
    if len(review_map) != len(tables["reviews.csv"]) or set(review_map) != {k for k, v in by_case.items() if "reviewer_approved" in v}:
        raise ArchiveBundleError("reviews.csv must contain one row for every reviewer-approved ruling only")
    for row in tables["reviews.csv"]:
        if row["reason_code"] not in {"policy_misapplied", "evidence_misweighted", "evidence_missing", "fraud_suspected", "goodwill", "safety_override", "other"}:
            raise ArchiveBundleError("reviews.csv has an unsupported reason_code")
        if row["agreed_with_agent"].lower() not in {"true", "false"}:
            raise ArchiveBundleError("reviews.csv agreed_with_agent must be true or false")
        row_time(row["reviewed_at"])
        for key in ("changed_fields", "reweighted_evidence"):
            try:
                json.loads(row[key])
            except json.JSONDecodeError as exc:
                raise ArchiveBundleError(f"reviews.csv {key} must be JSON") from exc
    evidence = tables["evidence.csv"]
    evidence_keys = [row["source_evidence_key"] for row in evidence]
    if any(not key.strip() for key in evidence_keys) or len(evidence_keys) != len(set(evidence_keys)):
        raise ArchiveBundleError("evidence.csv source keys must be non-empty and unique")
    for row in evidence:
        if row["source_case_key"] not in case_map:
            raise ArchiveBundleError("evidence.csv references an unknown case")
        if row["evidence_class"] not in {"gps_telemetry", "chat_log", "fare", "profile_history", "attachment", "external"}:
            raise ArchiveBundleError("evidence.csv has an unsupported evidence class")
        if row["source"] not in {"system_record", "rider_submitted", "driver_submitted", "external"}:
            raise ArchiveBundleError("evidence.csv has an unsupported evidence source")
        if row["visibility"] not in {"both", "rider_only", "driver_only", "reviewer_only"}:
            raise ArchiveBundleError("evidence.csv has an unsupported visibility")
        try:
            row_time(row["recorded_at"])
            for key in ("provenance", "verification", "payload"):
                json.loads(row[key])
        except (ValueError, json.JSONDecodeError) as exc:
            raise ArchiveBundleError("evidence timestamp and JSON fields must be valid") from exc


def row_time(value: str):
    from datetime import datetime

    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp must include UTC offset")
    return result
