"""Append separately namespaced case-history snapshots and rulings."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .bundle import ArchiveBundle


@dataclass(frozen=True)
class ArchiveImportResult:
    imported_users: int
    imported_trips: int
    imported_cases: int
    mapping_csv: str


def _identifier(conn, seq: str, prefix: str, role: str | None = None) -> str:
    value = conn.execute(
        "SELECT nextval(%s::regclass) AS generated_id", (seq,)
    ).fetchone()["generated_id"]
    if value > 999999:
        raise ValueError(f"shared internal ID range exhausted for {prefix}")
    return f"{prefix}-{role}-{value:06d}" if role else f"{prefix}-{value:06d}"


def _case_identifier(conn) -> str:
    """Allocate case IDs from the backend-owned global live/archive sequence."""
    value = conn.execute("SELECT nextval('tribunal.case_id_seq') AS generated_id").fetchone()["generated_id"]
    if value > 999999:
        raise ValueError("global dispute case ID range exhausted")
    return f"DSP-{value:06d}"


def import_bundle(database_url: str, bundle: ArchiveBundle) -> ArchiveImportResult:
    if bundle.manifest.get("synthetic") is not True:
        raise ValueError("archive importer accepts synthetic dataset bundles only")
    namespace = str(bundle.manifest["source_system"])
    users = {r["source_user_key"]: r for r in bundle.tables["users.csv"]}
    trips = {r["source_trip_key"]: r for r in bundle.tables["trips.csv"]}
    cases = {r["source_case_key"]: r for r in bundle.tables["cases.csv"]}
    rulings: dict[str, list[dict[str, str]]] = {key: [] for key in cases}
    reviews = {r["source_case_key"]: r for r in bundle.tables["reviews.csv"]}
    evidence_by_case: dict[str, list[dict[str, str]]] = {key: [] for key in cases}
    for row in bundle.tables["evidence.csv"]:
        evidence_by_case[row["source_case_key"]].append(dict(row))
    for row in bundle.tables["rulings.csv"]:
        rulings[row["source_case_key"]].append(dict(row))
    user_ids: dict[str, str] = {}
    trip_ids: dict[str, str] = {}
    case_ids: dict[str, str] = {}
    evidence_ids: dict[str, str] = {}
    counts = {"users": 0, "trips": 0, "cases": 0}
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.transaction():
            for key, row in users.items():
                scoped = f"{namespace}:{key}"
                existing = conn.execute("SELECT archive_user_id FROM case_archive.archive_user_snapshots WHERE bundle_user_key=%s", (scoped,)).fetchone()
                if existing:
                    user_ids[key] = existing["archive_user_id"]
                    continue
                role_code = "R" if row["role"] == "rider" else "D"
                sequence = (
                    "ride_data.imported_rider_id_seq"
                    if row["role"] == "rider"
                    else "ride_data.imported_driver_id_seq"
                )
                internal = _identifier(conn, sequence, "USR", role_code)
                conn.execute(
                    """INSERT INTO case_archive.archive_user_snapshots
                    (archive_user_id,bundle_user_key,role,display_name,account_age_days,average_rating,total_trips)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (internal, scoped, row["role"], row["display_name"], int(row["account_age_days"]),
                     Decimal(row["average_rating"]) if row["average_rating"] else None,
                     int(row["total_trips"]) if row["total_trips"] else None),
                )
                user_ids[key] = internal
                counts["users"] += 1
            for key, row in trips.items():
                scoped = f"{namespace}:{key}"
                existing = conn.execute("SELECT archive_ride_id FROM case_archive.archive_trip_snapshots WHERE bundle_trip_key=%s", (scoped,)).fetchone()
                if existing:
                    trip_ids[key] = existing["archive_ride_id"]
                    continue
                internal = _identifier(conn, "ride_data.imported_ride_id_seq", "RIDE")
                conn.execute(
                    """INSERT INTO case_archive.archive_trip_snapshots
                    (archive_ride_id,bundle_trip_key,rider_archive_user_id,driver_archive_user_id,trip_status,
                     trip_at,requested_at,accepted_at,pickup_at,dropoff_at,service_tier,quoted_distance_meters,
                     quoted_duration_seconds,quoted_fare_cents,fare_cents,currency,rider_rating,driver_rating,
                     fare_breakdown,pricing_structure,pickup_details,dropoff_details,gps_data)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (internal, scoped, user_ids[row["rider_source_user_key"]], user_ids[row["driver_source_user_key"]],
                     row["trip_status"], row["trip_at"],row["requested_at"],row["accepted_at"] or None,
                     row["pickup_at"] or None,row["dropoff_at"] or None,row["service_tier"],
                     int(row["quoted_distance_meters"]) if row["quoted_distance_meters"] else None,
                     int(row["quoted_duration_seconds"]) if row["quoted_duration_seconds"] else None,
                     int(row["quoted_fare_cents"]) if row["quoted_fare_cents"] else None,
                     int(row["fare_cents"]) if row["fare_cents"] else None,row["currency"],
                     Decimal(row["rider_rating"]) if row["rider_rating"] else None,
                     Decimal(row["driver_rating"]) if row["driver_rating"] else None,
                     Jsonb(json.loads(row["fare_breakdown"])),Jsonb(json.loads(row["pricing_structure"])), Jsonb(json.loads(row["pickup_details"])),
                     Jsonb(json.loads(row["dropoff_details"])), Jsonb(json.loads(row["gps_data"]))),
                )
                trip_ids[key] = internal
                counts["trips"] += 1
            for key, row in cases.items():
                scoped = f"{namespace}:{key}"
                existing = conn.execute("SELECT archive_case_id FROM case_archive.archive_cases WHERE bundle_case_key=%s", (scoped,)).fetchone()
                if existing:
                    case_ids[key] = existing["archive_case_id"]
                    continue
                internal = _case_identifier(conn)
                filer_id = user_ids[row["filing_user_source_key"]]
                conn.execute(
                    """INSERT INTO case_archive.archive_cases
                    (archive_case_id,archive_ride_id,category,subject,filed_by,created_at,policy_version,synthetic,
                     filing_archive_user_id,bundle_case_key)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,true,%s,%s)""",
                    (internal, trip_ids[row["source_trip_key"]], row["category"], row["subject"], row["filed_by"],
                     row["created_at"], row["policy_version"], filer_id, scoped),
                )
                conn.execute(
                    """INSERT INTO case_archive.archive_case_classifications
                    (archive_case_id,primary_classification,secondary_classifications,subject,monetary_impact_cents,fraud_risk)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (internal, row["primary_classification"], Jsonb(json.loads(row["secondary_classifications"])),
                     row["subject"], int(row["monetary_impact_cents"]), Decimal(row["fraud_risk"])),
                )
                case_ids[key] = internal
                counts["cases"] += 1
            for key, source_rows in evidence_by_case.items():
                case_id = case_ids[key]
                for row in source_rows:
                    scoped = f"{namespace}:{row['source_evidence_key']}"
                    existing = conn.execute(
                        "SELECT archive_evidence_id FROM case_archive.archive_case_evidence WHERE bundle_evidence_key=%s", (scoped,)
                    ).fetchone()
                    if existing:
                        evidence_ids[row["source_evidence_key"]] = existing["archive_evidence_id"]
                        continue
                    evidence_id = _identifier(conn, "ride_data.imported_evidence_id_seq", "EV")
                    conn.execute(
                        """INSERT INTO case_archive.archive_case_evidence
                        (archive_evidence_id,archive_case_id,evidence_class,source,recorded_at,provenance,
                         verification,visibility,payload,synthetic,bundle_evidence_key)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s)""",
                        (evidence_id,case_id,row["evidence_class"],row["source"],row["recorded_at"],
                         Jsonb(json.loads(row["provenance"])),Jsonb(json.loads(row["verification"])),
                         row["visibility"],Jsonb(json.loads(row["payload"])),scoped),
                    )
                    evidence_ids[row["source_evidence_key"]] = evidence_id
            for key, source_rows in rulings.items():
                case_id = case_ids[key]
                if conn.execute("SELECT 1 FROM case_archive.archive_case_decisions WHERE archive_case_id=%s", (case_id,)).fetchone():
                    continue
                mapped_rows = []
                for row in source_rows:
                    conn.execute(
                        """INSERT INTO case_archive.archive_case_rulings
                        (archive_case_id,ruling_stage,decision_origin,verdict,ruling_type,action_description,
                         amount_cents,currency,confidence,decided_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (case_id,row["stage"],row["origin"],row["verdict"],row["ruling_type"],row["action_description"],
                         int(row["amount_cents"]),row["currency"],Decimal(row["confidence"]) if row["confidence"] else None,row["decided_at"]),
                    )
                    mapped_rows.append(row)
                approved = next((r for r in mapped_rows if r["stage"] == "reviewer_approved"), None)
                final = approved or next(r for r in mapped_rows if r["stage"] == "model_proposed")
                conn.execute(
                    """INSERT INTO case_archive.archive_case_decisions
                    (archive_case_id,verdict,ruling_type,recommended_action_description,recommended_amount_cents,
                     currency,confidence,decision_origin,decided_at,synthetic)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,true)""",
                    (case_id,final["verdict"],final["ruling_type"],final["action_description"],int(final["amount_cents"]),
                     final["currency"],Decimal(final["confidence"]) if final["confidence"] else None,
                     final["origin"],final["decided_at"]),
                )
                review = reviews.get(key)
                conn.execute(
                    """INSERT INTO case_archive.archive_human_reviews
                    (archive_case_id,human_reviewed,changed_fields,reason_code,rationale,agreed_with_agent,
                     reweighted_evidence,reviewed_at,synthetic)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,true)""",
                    (case_id, approved is not None,
                     Jsonb(json.loads(review["changed_fields"])) if review else Jsonb([]),
                     (review["reason_code"] or "other") if review else None,
                     review["rationale"] if review else "No human review recorded in archive bundle.",
                     (review["agreed_with_agent"].lower() == "true") if review and review["agreed_with_agent"] else None,
                     Jsonb(json.loads(review["reweighted_evidence"])) if review else Jsonb([]),
                     review["reviewed_at"] if review else None),
                )
                case = cases[key]
                conn.execute(
                    """INSERT INTO case_archive.archive_precedent_index
                    (archive_case_id,category,feature_vector,summary,policy_version)
                    VALUES (%s,%s,%s,%s,%s)""",
                    (case_id,case["category"],Jsonb({"category":case["category"],"human_reviewed":approved is not None}),
                     f"Archive precedent {case_id} ({case['category']})",case["policy_version"]),
                )
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["source_system", "record_type", "source_key", "internal_id"])
    for kind, mapping in (("user", user_ids), ("trip", trip_ids), ("case", case_ids), ("evidence", evidence_ids)):
        for key, value in sorted(mapping.items()):
            writer.writerow([namespace, kind, key, value or ""])
    return ArchiveImportResult(counts["users"], counts["trips"], counts["cases"], stream.getvalue())
