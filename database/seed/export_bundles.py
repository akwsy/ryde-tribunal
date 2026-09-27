"""Export seeded synthetic users/trips and archive history as separate importer ZIPs."""
from __future__ import annotations

import argparse
import csv
import json
import os
import zipfile
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

RIDE_SOURCE_NAMESPACE = "ryde-tribunal-synthetic-seed"


def _csv_bytes(headers: list[str], rows) -> bytes:
    from io import StringIO

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _value(value) for key, value in row.items()})
    return stream.getvalue().encode("utf-8")


def _value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "" if value is None else value


def _zip(path: Path, members: dict[str, bytes]) -> None:
    if path.exists():
        raise FileExistsError(f"output already exists: {path}")
    if not path.parent.is_dir():
        raise FileNotFoundError(f"output folder does not exist: {path.parent}")
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def export(database_url: str, company_out: Path, archive_out: Path) -> tuple[int, int, int, int, int]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        users = conn.execute(
            """SELECT e.company_user_id,u.role,coalesce(u.full_name,u.display_handle) AS name,
              p.account_age_days,p.total_trips,p.average_rating,p.dispute_history_total,
              p.dispute_history_upheld,p.dispute_history_rejected,p.dispute_history_upheld_against,
              p.fraud_flag_count,p.fraud_flag_details,p.payment_method,p.vehicle
            FROM ride_data.users u JOIN ride_data.user_profiles p USING (user_id)
            JOIN ride_data.external_user_ids e USING (user_id)
            WHERE u.synthetic IS TRUE AND p.synthetic IS TRUE AND e.source_system=%s ORDER BY u.user_id""",
            (RIDE_SOURCE_NAMESPACE,),
        ).fetchall()
        trips = conn.execute(
            """SELECT et.company_trip_id,er.company_user_id AS company_rider_id,
              ed.company_user_id AS company_driver_id,coalesce(r.scheduled_at,r.requested_at) AS scheduled_time,
              rp.driver_arrival_at AS driver_arrival_time,rp.driver_wait_start_at AS driver_wait_start,
              r.cancellation_at AS cancellation_time,r.cancellation_reason,
              coalesce(f.cancellation_fee_cents,0)::numeric/100 AS cancellation_fee,
              rp.pickup_label AS pickup_location_name,rp.pickup_lat AS pickup_lat,rp.pickup_lon AS pickup_lng,
              rp.dropoff_label AS dropoff_location_name,rp.dropoff_lat AS dropoff_lat,rp.dropoff_lon AS dropoff_lng,
              r.ride_status,r.service_tier,r.quoted_distance_meters,r.quoted_duration_seconds,r.quoted_fare_cents,
              r.currency, f.base_fare_cents,f.distance_fare_cents,f.time_fare_cents,f.waiting_fare_cents,
              f.surge_multiplier,f.surge_fare_cents,f.platform_fee_cents,f.total_fare_cents
            FROM ride_data.rides r JOIN ride_data.ride_route_plans rp USING (ride_id)
            LEFT JOIN ride_data.ride_fare_breakdowns f USING (ride_id)
            JOIN ride_data.external_trip_ids et USING (ride_id)
            JOIN ride_data.external_user_ids er ON er.user_id=r.rider_user_id AND er.source_system=%s
            JOIN ride_data.external_user_ids ed ON ed.user_id=r.driver_user_id AND ed.source_system=%s
            WHERE r.synthetic IS TRUE AND et.source_system=%s ORDER BY r.ride_id""",
            (RIDE_SOURCE_NAMESPACE, RIDE_SOURCE_NAMESPACE, RIDE_SOURCE_NAMESPACE),
        ).fetchall()
        ratings = conn.execute(
            """SELECT et.company_trip_id,eu.company_user_id AS company_rated_user_id,
              r.rating_from_role,r.rating,r.rated_at
            FROM ride_data.ride_ratings r JOIN ride_data.rides t USING (ride_id)
            JOIN ride_data.external_trip_ids et USING (ride_id)
            JOIN ride_data.external_user_ids eu ON eu.user_id=r.rated_user_id AND eu.source_system=%s
            WHERE r.synthetic IS TRUE AND t.synthetic IS TRUE AND et.source_system=%s
            ORDER BY et.company_trip_id,r.rated_user_id""",
            (RIDE_SOURCE_NAMESPACE, RIDE_SOURCE_NAMESPACE),
        ).fetchall()
        gps = conn.execute(
            """SELECT e.company_trip_id,sequence_no,sample_at AS timestamp,lat,lon AS lng,
              coalesce(speed_kmh,speed_meters_per_second*3.6) AS speed_kmh,status
            FROM ride_data.ride_gps_samples g JOIN ride_data.external_trip_ids e USING (ride_id)
            WHERE g.synthetic IS TRUE AND e.source_system=%s ORDER BY e.company_trip_id,sample_at,sample_id""",
            (RIDE_SOURCE_NAMESPACE,),
        ).fetchall()
        chats = conn.execute(
            """SELECT e.company_trip_id,sequence_no,sent_at AS timestamp,participant_role AS sender,
              message_type AS type,message_text AS content FROM ride_data.ride_chat_messages g
            JOIN ride_data.external_trip_ids e USING (ride_id)
            WHERE g.synthetic IS TRUE AND e.source_system=%s ORDER BY e.company_trip_id,sent_at,message_id""",
            (RIDE_SOURCE_NAMESPACE,),
        ).fetchall()
        events = conn.execute(
            """SELECT e.company_trip_id,sequence_no,event_at AS timestamp,event_type,details
            FROM ride_data.ride_app_events g JOIN ride_data.external_trip_ids e USING (ride_id)
            WHERE g.synthetic IS TRUE AND e.source_system=%s ORDER BY e.company_trip_id,sequence_no""",
            (RIDE_SOURCE_NAMESPACE,),
        ).fetchall()
        metadata = []
        for user in users:
            metadata.append({"record_type":"profile","company_trip_id":"","company_user_id":user["company_user_id"],"sequence_no":"","verification_status":"verified","verified_by":"synthetic_seed","verified_at":"","evidence_source":"system_record"})
        for trip in trips:
            for kind in ("trip","route","fare"):
                metadata.append({"record_type":kind,"company_trip_id":trip["company_trip_id"],"company_user_id":"","sequence_no":"","verification_status":"verified","verified_by":"synthetic_seed","verified_at":"","evidence_source":"system_record"})
        for filename, rows, kind in (("gps_telemetry.csv",gps,"gps_telemetry"),("chat_logs.csv",chats,"chat_log"),("app_events.csv",events,"app_event")):
            counts = {}
            for row in rows:
                key = row["company_trip_id"]
                order = counts.get(key, 0)
                counts[key] = order + 1
                metadata.append({"record_type":kind,"company_trip_id":key,"company_user_id":"","sequence_no":str(order),"verification_status":"verified","verified_by":"synthetic_seed","verified_at":"","evidence_source":"system_record"})
        user_rows = [{"company_user_id":u["company_user_id"],"role":u["role"],"name":u["name"] or "Synthetic user"} for u in users]
        profile_rows = [{"company_user_id":u["company_user_id"],"account_age_days":u["account_age_days"],"total_trips":u["total_trips"] or 0,"avg_rating":u["average_rating"],"dispute_history_total":u["dispute_history_total"] or 0,"dispute_history_upheld":u["dispute_history_upheld"] or 0,"dispute_history_rejected":u["dispute_history_rejected"] or 0,"dispute_history_upheld_against":u["dispute_history_upheld_against"] or 0,"fraud_flags":u["fraud_flag_count"] or 0,"fraud_flag_details":u["fraud_flag_details"] or "","payment_method":u["payment_method"] or "","vehicle":u["vehicle"] or ""} for u in users]
        trip_rows = []
        for trip in trips:
            fare = {name: trip[name] for name in ("base_fare_cents","distance_fare_cents","time_fare_cents","waiting_fare_cents","surge_multiplier","surge_fare_cents","platform_fee_cents","total_fare_cents","currency")}
            pricing = {"service_tier":trip["service_tier"],"quoted_distance_meters":trip["quoted_distance_meters"],"quoted_duration_seconds":trip["quoted_duration_seconds"],"surge_multiplier":trip["surge_multiplier"]}
            trip_rows.append({**trip,"fare_breakdown_json":json.dumps(fare,default=_value,separators=(",",":")),"pricing_structure":json.dumps(pricing,default=_value,separators=(",",":"))})

        company_members = {
            "manifest.json": json.dumps({"format_version":"1","source_system":RIDE_SOURCE_NAMESPACE,"synthetic":True},sort_keys=True).encode(),
            "users.csv": _csv_bytes(["company_user_id","role","name"],user_rows),
            "profiles.csv": _csv_bytes(["company_user_id","account_age_days","total_trips","avg_rating","dispute_history_total","dispute_history_upheld","dispute_history_rejected","dispute_history_upheld_against","fraud_flags","fraud_flag_details","payment_method","vehicle"],profile_rows),
            "trips.csv": _csv_bytes(["company_trip_id","company_rider_id","company_driver_id","pickup_location_name","pickup_lat","pickup_lng","dropoff_location_name","dropoff_lat","dropoff_lng","scheduled_time","driver_arrival_time","driver_wait_start","cancellation_time","cancellation_fee","cancellation_reason","ride_status","service_tier","quoted_distance_meters","quoted_duration_seconds","quoted_fare_cents","fare_breakdown_json","pricing_structure"],trip_rows),
            "gps_telemetry.csv": _csv_bytes(["company_trip_id","sequence_no","timestamp","lat","lng","speed_kmh","status"],gps),
            "chat_logs.csv": _csv_bytes(["company_trip_id","sequence_no","timestamp","sender","type","content"],chats),
            "app_events.csv": _csv_bytes(["company_trip_id","sequence_no","timestamp","event_type","details"],events),
            "ratings.csv": _csv_bytes(["company_trip_id","company_rated_user_id","rating_from_role","rating","rated_at"],ratings),
            "evidence_metadata.csv": _csv_bytes(["record_type","company_trip_id","company_user_id","sequence_no","verification_status","verified_by","verified_at","evidence_source"],metadata),
        }

        archive_users = conn.execute(
            "SELECT archive_user_id AS id,bundle_user_key AS source_user_key,role,display_name,account_age_days,average_rating,total_trips FROM case_archive.archive_user_snapshots WHERE synthetic IS TRUE ORDER BY archive_user_id"
        ).fetchall()
        archive_trips = conn.execute(
            """SELECT archive_ride_id AS id,bundle_trip_key AS source_trip_key,rider_archive_user_id,driver_archive_user_id,
              trip_status,trip_at,requested_at,accepted_at,pickup_at,dropoff_at,service_tier,quoted_distance_meters,
              quoted_duration_seconds,quoted_fare_cents,fare_cents,currency,rider_rating,driver_rating,fare_breakdown,
              pricing_structure,pickup_details,dropoff_details,gps_data
            FROM case_archive.archive_trip_snapshots WHERE synthetic IS TRUE ORDER BY archive_ride_id"""
        ).fetchall()
        archive_cases = conn.execute(
            """SELECT c.archive_case_id AS id,c.bundle_case_key AS source_case_key,c.archive_ride_id,
              c.filing_archive_user_id,c.category,c.subject,c.filed_by,c.created_at,c.policy_version,
              cl.primary_classification,cl.secondary_classifications,cl.monetary_impact_cents,cl.fraud_risk
            FROM case_archive.archive_cases c JOIN case_archive.archive_case_classifications cl USING (archive_case_id)
            WHERE c.synthetic IS TRUE ORDER BY c.archive_case_id"""
        ).fetchall()
        archive_rulings = conn.execute(
            """SELECT c.bundle_case_key AS source_case_key,r.ruling_stage AS stage,r.decision_origin AS origin,
              r.verdict,r.ruling_type,r.action_description,r.amount_cents,r.currency,r.confidence,r.decided_at
            FROM case_archive.archive_case_rulings r JOIN case_archive.archive_cases c USING (archive_case_id)
            WHERE r.synthetic IS TRUE AND c.synthetic IS TRUE ORDER BY c.archive_case_id,r.ruling_stage"""
        ).fetchall()
        archive_reviews = conn.execute(
            """SELECT c.bundle_case_key AS source_case_key,h.reason_code,h.rationale,h.agreed_with_agent,
              h.changed_fields,h.reweighted_evidence,h.reviewed_at
            FROM case_archive.archive_human_reviews h JOIN case_archive.archive_cases c USING (archive_case_id)
            WHERE h.synthetic IS TRUE AND h.human_reviewed IS TRUE ORDER BY c.archive_case_id"""
        ).fetchall()
        archive_evidence = conn.execute(
            """SELECT e.archive_evidence_id AS id,e.bundle_evidence_key AS source_evidence_key,
              c.bundle_case_key AS source_case_key,e.evidence_class,e.source,e.recorded_at,e.provenance,
              e.verification,e.visibility,e.payload
            FROM case_archive.archive_case_evidence e JOIN case_archive.archive_cases c USING (archive_case_id)
            WHERE e.synthetic IS TRUE AND c.synthetic IS TRUE ORDER BY e.archive_evidence_id"""
        ).fetchall()
        archive_user_keys = {row["id"]: row["source_user_key"].rsplit(":", 1)[-1] for row in archive_users}
        archive_trip_keys = {row["id"]: row["source_trip_key"].rsplit(":", 1)[-1] for row in archive_trips}
        archive_case_keys = {row["id"]: row["source_case_key"].rsplit(":", 1)[-1] for row in archive_cases}
        archive_case_rows = []
        for case in archive_cases:
            archive_case_rows.append({**case,"source_case_key":archive_case_keys[case["id"]],"source_trip_key":archive_trip_keys[case["archive_ride_id"]],"filing_user_source_key":archive_user_keys[case["filing_archive_user_id"]]})
        for ruling in archive_rulings:
            ruling["source_case_key"] = ruling["source_case_key"].rsplit(":", 1)[-1]
        for review in archive_reviews:
            review["source_case_key"] = review["source_case_key"].rsplit(":", 1)[-1]
        for evidence in archive_evidence:
            evidence["source_evidence_key"] = evidence["source_evidence_key"].rsplit(":", 1)[-1]
            evidence["source_case_key"] = evidence["source_case_key"].rsplit(":", 1)[-1]
        archive_members = {
            "manifest.json": json.dumps({"format_version":"1","source_system":"ryde-tribunal-synthetic-archive","synthetic":True},sort_keys=True).encode(),
            "users.csv": _csv_bytes(["source_user_key","role","display_name","account_age_days","average_rating","total_trips"],[{**u,"source_user_key":archive_user_keys[u["id"]]} for u in archive_users]),
            "trips.csv": _csv_bytes(["source_trip_key","rider_source_user_key","driver_source_user_key","trip_status","trip_at","requested_at","accepted_at","pickup_at","dropoff_at","service_tier","quoted_distance_meters","quoted_duration_seconds","quoted_fare_cents","fare_cents","currency","rider_rating","driver_rating","fare_breakdown","pricing_structure","pickup_details","dropoff_details","gps_data"],[{**r,"source_trip_key":archive_trip_keys[r["id"]],"rider_source_user_key":archive_user_keys[r["rider_archive_user_id"]],"driver_source_user_key":archive_user_keys[r["driver_archive_user_id"]]} for r in archive_trips]),
            "cases.csv": _csv_bytes(["source_case_key","source_trip_key","filing_user_source_key","category","subject","filed_by","created_at","policy_version","primary_classification","secondary_classifications","monetary_impact_cents","fraud_risk"],archive_case_rows),
            "rulings.csv": _csv_bytes(["source_case_key","stage","origin","verdict","ruling_type","action_description","amount_cents","currency","confidence","decided_at"],archive_rulings),
            "reviews.csv": _csv_bytes(["source_case_key","reason_code","rationale","agreed_with_agent","changed_fields","reweighted_evidence","reviewed_at"],archive_reviews),
            "evidence.csv": _csv_bytes(["source_evidence_key","source_case_key","evidence_class","source","recorded_at","provenance","verification","visibility","payload"],archive_evidence),
        }
    _zip(company_out, company_members)
    _zip(archive_out, archive_members)
    return len(users), len(trips), len(ratings), len(archive_users), len(archive_cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "postgresql:///ryde_tribunal"))
    parser.add_argument("--company-out", type=Path, required=True)
    parser.add_argument("--archive-out", type=Path, required=True)
    args = parser.parse_args()
    counts = export(args.database_url, args.company_out, args.archive_out)
    print(f"Exported {counts[0]} users, {counts[1]} trips, {counts[2]} ratings, "
          f"{counts[3]} archive-party snapshots, and {counts[4]} disputes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
