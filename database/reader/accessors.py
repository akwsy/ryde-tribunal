from __future__ import annotations

import os
import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .models import (
    ArchiveCase,
    ArchiveDecision,
    ArchiveHistoryRecord,
    ArchiveRuling,
    ArchiveSearchResult,
    ArchiveTripSnapshot,
    ArchiveUserSnapshot,
    AppEvent,
    ChatMessage,
    DisputeCounters,
    EvidenceReference,
    FareAdjustment,
    FareBreakdown,
    GpsSample,
    HumanReview,
    Money,
    Profile,
    PromoApplication,
    RatingPoint,
    RideHeader,
    RideSearchResult,
    Route,
    Stop,
    Waypoint,
    as_utc,
)

DEFAULT_DATABASE_URL = "postgresql:///ryde_tribunal"
MAX_RIDE_SEARCH_LIMIT = 100


def _connect() -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL), row_factory=dict_row)


def _one(cur: psycopg.Cursor[dict[str, Any]], label: str) -> dict[str, Any]:
    row = cur.fetchone()
    if row is None:
        raise LookupError(f"{label} not found")
    return dict(row)


def _money(amount_cents: int, currency: str) -> Money:
    return Money.model_validate({"amount_cents": amount_cents, "currency": currency})


def _archive_ruling(row: dict[str, Any]) -> ArchiveRuling:
    return ArchiveRuling.model_validate({
        "stage": row["ruling_stage"],
        "decision": {
            "verdict": row["verdict"],
            "ruling_type": row["ruling_type"],
            "recommended_action_description": row["action_description"],
            "recommended_amount": _money(row["amount_cents"], row["currency"]),
            "confidence": row["confidence"],
            "decision_origin": row["decision_origin"],
            "decided_at": as_utc(row["decided_at"]),
            "synthetic": row["synthetic"],
        },
    })


def _optional_money(amount_cents: int | None, currency: str) -> Money | None:
    return None if amount_cents is None else _money(amount_cents, currency)


def get_ride(ride_id: str) -> RideHeader:
    with _connect() as conn:
        row = _one(
            conn.execute(
                """
                SELECT r.ride_id, x.company_trip_id, x.source_system,
                       r.rider_user_id, r.driver_user_id, r.requested_at, r.scheduled_at,
                       r.accepted_at, r.pickup_at, r.dropoff_at, r.cancellation_at,
                       r.cancellation_reason, r.ride_status, r.service_tier,
                       r.quoted_distance_meters, r.quoted_duration_seconds, r.quoted_fare_cents,
                       r.currency, f.total_fare_cents, f.cancellation_fee_cents,
                       r.evidence_source, r.verification_status, r.verified_by, r.verified_at,
                       r.provenance, r.synthetic
                FROM ride_data.rides r
                LEFT JOIN ride_data.external_trip_ids x USING (ride_id)
                LEFT JOIN ride_data.ride_fare_breakdowns f USING (ride_id)
                WHERE r.ride_id = %s
                """,
                (ride_id,),
            ),
            ride_id,
        )
    return RideHeader.model_validate(
        {
            "ride_id": row["ride_id"],
            "company_trip_id": row["company_trip_id"],
            "source_system": row["source_system"],
            "rider_user_id": row["rider_user_id"],
            "driver_user_id": row["driver_user_id"],
            "requested_at": as_utc(row["requested_at"]),
            "scheduled_at": as_utc(row["scheduled_at"]),
            "accepted_at": as_utc(row["accepted_at"]),
            "pickup_at": as_utc(row["pickup_at"]),
            "dropoff_at": as_utc(row["dropoff_at"]),
            "cancellation_at": as_utc(row["cancellation_at"]),
            "cancellation_reason": row["cancellation_reason"],
            "ride_status": row["ride_status"],
            "service_tier": row["service_tier"],
            "quoted_distance_meters": row["quoted_distance_meters"],
            "quoted_duration_seconds": row["quoted_duration_seconds"],
            "quoted_fare": _optional_money(row["quoted_fare_cents"], row["currency"]),
            "fare_total": _optional_money(row["total_fare_cents"], row["currency"]),
            "cancellation_fee": _optional_money(row["cancellation_fee_cents"], row["currency"]),
            "evidence_source": row["evidence_source"],
            "verification_status": row["verification_status"],
            "verified_by": row["verified_by"],
            "verified_at": as_utc(row["verified_at"]),
            "provenance": row["provenance"],
            "synthetic": row["synthetic"],
        }
    )


def search_rides(query: str = "", limit: int = 20) -> list[RideSearchResult]:
    """Search selectable live rides by internal ID, company ID, names, or locations.

    A blank query returns the most recently booked rides, which lets the filing UI
    display a useful first page as soon as the trip picker receives focus.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    bounded_limit = min(limit, MAX_RIDE_SEARCH_LIMIT)
    normalized_query = query.strip()
    if normalized_query:
        escaped_query = normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_query}%"
    else:
        pattern = None
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.ride_id, x.company_trip_id, x.source_system,
                   COALESCE(r.scheduled_at, r.requested_at) AS booked_at,
                   r.ride_status, p.pickup_label, p.dropoff_label,
                   COALESCE(rider.full_name, rider.display_handle) AS rider_name,
                   COALESCE(driver.full_name, driver.display_handle) AS driver_name
            FROM ride_data.rides r
            LEFT JOIN ride_data.external_trip_ids x USING (ride_id)
            LEFT JOIN ride_data.ride_route_plans p USING (ride_id)
            JOIN ride_data.users rider ON rider.user_id = r.rider_user_id
            JOIN ride_data.users driver ON driver.user_id = r.driver_user_id
               WHERE %s::text IS NULL
               OR r.ride_id ILIKE %s ESCAPE E'\\\\'
               OR x.company_trip_id ILIKE %s ESCAPE E'\\\\'
               OR p.pickup_label ILIKE %s ESCAPE E'\\\\'
               OR p.dropoff_label ILIKE %s ESCAPE E'\\\\'
               OR rider.full_name ILIKE %s ESCAPE E'\\\\'
               OR rider.display_handle ILIKE %s ESCAPE E'\\\\'
               OR driver.full_name ILIKE %s ESCAPE E'\\\\'
               OR driver.display_handle ILIKE %s ESCAPE E'\\\\'
            ORDER BY COALESCE(r.scheduled_at, r.requested_at) DESC NULLS LAST, r.ride_id DESC
            LIMIT %s
            """,
            (pattern, pattern, pattern, pattern, pattern, pattern, pattern, pattern, pattern, bounded_limit),
        ).fetchall()
    return [
        RideSearchResult.model_validate({**dict(row), "booked_at": as_utc(row["booked_at"])})
        for row in rows
    ]


def get_route(ride_id: str) -> Route:
    with _connect() as conn:
        route = _one(
            conn.execute(
                """
                SELECT p.*, x.source_system
                FROM ride_data.ride_route_plans p
                LEFT JOIN ride_data.external_trip_ids x USING (ride_id)
                WHERE p.ride_id = %s
                """,
                (ride_id,),
            ),
            ride_id,
        )
        waypoint_rows = conn.execute(
            "SELECT route_kind, sequence_no, lat, lon, label, recorded_at, synthetic FROM ride_data.ride_waypoints WHERE ride_id = %s ORDER BY route_kind, sequence_no",
            (ride_id,),
        ).fetchall()
        stop_rows = conn.execute(
            "SELECT started_at, ended_at, duration_seconds, lat, lon, rider_requested, note, synthetic FROM ride_data.ride_stops WHERE ride_id = %s ORDER BY started_at",
            (ride_id,),
        ).fetchall()
    return Route.model_validate(
        {
            **route,
            "driver_arrival_at": as_utc(route["driver_arrival_at"]),
            "driver_wait_start_at": as_utc(route["driver_wait_start_at"]),
            "verified_at": as_utc(route["verified_at"]),
            "waypoints": [Waypoint.model_validate({**dict(row), "recorded_at": as_utc(row["recorded_at"])}) for row in waypoint_rows],
            "stops": [Stop.model_validate({**dict(row), "started_at": as_utc(row["started_at"]), "ended_at": as_utc(row["ended_at"])}) for row in stop_rows],
        }
    )


def get_gps_samples(ride_id: str) -> list[GpsSample]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sample_id, ride_id, sample_at, sequence_no, lat, lon, accuracy_meters, speed_meters_per_second, speed_kmh, status, collector, source_system, evidence_source, verification_status, verified_by, verified_at, provenance, synthetic FROM ride_data.ride_gps_samples WHERE ride_id = %s ORDER BY sequence_no NULLS LAST, sample_at, sample_id",
            (ride_id,),
        ).fetchall()
    return [GpsSample.model_validate({**dict(row), "sample_at": as_utc(row["sample_at"]), "verified_at": as_utc(row["verified_at"])}) for row in rows]


def get_chat_log(ride_id: str) -> list[ChatMessage]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT message_id, ride_id, participant_role, sent_at, message_text, sequence_no, message_type, source_system, evidence_source, verification_status, verified_by, verified_at, provenance, synthetic FROM ride_data.ride_chat_messages WHERE ride_id = %s ORDER BY sequence_no NULLS LAST, sent_at, message_id",
            (ride_id,),
        ).fetchall()
    return [ChatMessage.model_validate({**dict(row), "sent_at": as_utc(row["sent_at"]), "verified_at": as_utc(row["verified_at"])}) for row in rows]


def get_app_events(ride_id: str) -> list[AppEvent]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT event_id, ride_id, sequence_no, event_at, event_type, details,
                   source_system, evidence_source, verification_status, verified_by,
                   verified_at, provenance, synthetic
            FROM ride_data.ride_app_events
            WHERE ride_id = %s
            ORDER BY sequence_no, event_id
            """,
            (ride_id,),
        ).fetchall()
    return [AppEvent.model_validate({**dict(row), "event_at": as_utc(row["event_at"]), "verified_at": as_utc(row["verified_at"])}) for row in rows]


def get_fare_breakdown(ride_id: str) -> FareBreakdown:
    with _connect() as conn:
        row = _one(
            conn.execute(
                """
                SELECT f.*, x.source_system
                FROM ride_data.ride_fare_breakdowns f
                LEFT JOIN ride_data.external_trip_ids x USING (ride_id)
                WHERE f.ride_id = %s
                """,
                (ride_id,),
            ),
            ride_id,
        )
        adjustments = conn.execute(
            "SELECT adjustment_type, amount_cents, currency, applied_at, synthetic FROM ride_data.ride_fare_adjustments WHERE ride_id = %s ORDER BY adjustment_id",
            (ride_id,),
        ).fetchall()
        promos = conn.execute(
            "SELECT promo_code, amount_cents, currency, applied_at, synthetic FROM ride_data.ride_promo_applications WHERE ride_id = %s ORDER BY promo_id",
            (ride_id,),
        ).fetchall()
    return FareBreakdown.model_validate(
        {
            "ride_id": row["ride_id"],
            "base_fare": _optional_money(row["base_fare_cents"], row["currency"]),
            "distance_fare": _optional_money(row["distance_fare_cents"], row["currency"]),
            "time_fare": _optional_money(row["time_fare_cents"], row["currency"]),
            "waiting_fare": _optional_money(row["waiting_fare_cents"], row["currency"]),
            "surge_multiplier": row["surge_multiplier"],
            "surge_fare": _optional_money(row["surge_fare_cents"], row["currency"]),
            "cancellation_fee": _optional_money(row["cancellation_fee_cents"], row["currency"]),
            "platform_fee": _optional_money(row["platform_fee_cents"], row["currency"]),
            "total_fare": _optional_money(row["total_fare_cents"], row["currency"]),
            "adjustments": [
                FareAdjustment.model_validate({"adjustment_type": r["adjustment_type"], "amount": {"amount_cents": r["amount_cents"], "currency": r["currency"]}, "applied_at": as_utc(r["applied_at"]), "synthetic": r["synthetic"]})
                for r in adjustments
            ],
            "promos": [
                PromoApplication.model_validate({"promo_code": r["promo_code"], "amount": {"amount_cents": r["amount_cents"], "currency": r["currency"]}, "applied_at": as_utc(r["applied_at"]), "synthetic": r["synthetic"]})
                for r in promos
            ],
            "source_system": row["source_system"],
            "evidence_source": row["evidence_source"],
            "verification_status": row["verification_status"],
            "verified_by": row["verified_by"],
            "verified_at": as_utc(row["verified_at"]),
            "provenance": row["provenance"],
            "synthetic": row["synthetic"],
        }
    )


def get_profile(user_id: str) -> Profile:
    with _connect() as conn:
        row = _one(
            conn.execute(
                """
                SELECT u.user_id, x.company_user_id, x.source_system, u.role, u.display_handle,
                       u.full_name, u.created_at, p.account_age_days, p.lifetime_completed_rides,
                       p.total_trips, p.average_rating, p.rating_trend,
                       p.dispute_history_total, p.dispute_history_upheld,
                       p.dispute_history_rejected, p.dispute_history_upheld_against,
                       p.fraud_flag_count, p.fraud_flag_details, p.payment_method, p.vehicle,
                       p.evidence_source, p.verification_status, p.verified_by, p.verified_at,
                       p.provenance, p.synthetic
                FROM ride_data.users u
                JOIN ride_data.user_profiles p USING (user_id)
                LEFT JOIN ride_data.external_user_ids x USING (user_id)
                WHERE u.user_id = %s
                """,
                (user_id,),
            ),
            user_id,
        )
        counters = conn.execute("SELECT * FROM ride_data.user_dispute_counters WHERE user_id = %s", (user_id,)).fetchone()
        ratings = conn.execute(
            "SELECT rating_at, rating, sample_size, synthetic FROM ride_data.user_rating_history WHERE user_id = %s ORDER BY rating_at",
            (user_id,),
        ).fetchall()
    dispute_counts = None
    prior_classifications = None
    if counters is not None:
        counter_values = {k: v for k, v in counters.items() if k not in {"user_id", "synthetic"}}
        if any(value is not None for value in counter_values.values()):
            dispute_counts = DisputeCounters.model_validate({
                **counter_values,
                "synthetic": counters["synthetic"],
            })
        count_fields = ("route_deviation_count", "no_show_count", "property_damage_count", "safety_incident_count")
        if all(counters[name] is not None for name in count_fields):
            prior_classifications = (
                ["route_deviation"] * counters["route_deviation_count"]
                + ["no_show_charge"] * counters["no_show_count"]
                + ["property_damage"] * counters["property_damage_count"]
                + ["safety_incident"] * counters["safety_incident_count"]
            )
    company_history_values = {
        "total": row["dispute_history_total"],
        "upheld": row["dispute_history_upheld"],
        "rejected": row["dispute_history_rejected"],
        "upheld_against": row["dispute_history_upheld_against"],
    }
    company_history = None
    if any(value is not None for value in company_history_values.values()):
        company_history = company_history_values
    profile_payload = {
        key: value for key, value in row.items()
        if key not in {
            "dispute_history_total",
            "dispute_history_upheld",
            "dispute_history_rejected",
            "dispute_history_upheld_against",
        }
    }
    return Profile.model_validate(
        {
            **profile_payload,
            "created_at": as_utc(row["created_at"]),
            "verified_at": as_utc(row["verified_at"]),
            "company_dispute_history": company_history,
            "dispute_counts": dispute_counts,
            "rating_history": [RatingPoint.model_validate({**dict(r), "rating_at": as_utc(r["rating_at"])}) for r in ratings],
            "prior_classifications": prior_classifications,
        }
    )


def get_archive_case(archive_case_id: str) -> ArchiveCase:
    if not re.fullmatch(r"^DSP-\d{6}$", archive_case_id):
        raise ValueError(f"archive case id must match ^DSP-\\d{{6}}$; got {archive_case_id!r}")
    with _connect() as conn:
        # Query the archive relation only. Shared allocation and the one-time remap guarantee
        # that a live case ID has no archive row with the same value; an absent row fails below.
        row = _one(
            conn.execute(
                """
                SELECT c.*, cl.primary_classification, cl.secondary_classifications,
                       cl.monetary_impact_cents, cl.fraud_risk
                FROM case_archive.archive_cases c
                JOIN case_archive.archive_case_classifications cl USING (archive_case_id)
                WHERE c.archive_case_id = %s
                """,
                (archive_case_id,),
            ),
            archive_case_id,
        )
        evidence = conn.execute(
            "SELECT archive_evidence_id AS evidence_id, evidence_class, source, recorded_at, visibility, provenance, verification, payload, synthetic FROM case_archive.archive_case_evidence WHERE archive_case_id = %s ORDER BY archive_evidence_id",
            (archive_case_id,),
        ).fetchall()
        decision_row = _one(conn.execute("SELECT * FROM case_archive.archive_case_decisions WHERE archive_case_id = %s", (archive_case_id,)), archive_case_id)
        review_row = _one(conn.execute("SELECT * FROM case_archive.archive_human_reviews WHERE archive_case_id = %s", (archive_case_id,)), archive_case_id)
        ruling_rows = conn.execute(
            """SELECT ruling_stage,decision_origin,verdict,ruling_type,action_description,amount_cents,
              currency,confidence,decided_at,synthetic
            FROM case_archive.archive_case_rulings WHERE archive_case_id=%s
            ORDER BY CASE ruling_stage WHEN 'model_proposed' THEN 0 ELSE 1 END""",
            (archive_case_id,),
        ).fetchall()
        trip_row = _one(conn.execute(
            """SELECT t.*,ru.archive_user_id AS rider_id,ru.role AS rider_role,ru.display_name AS rider_name,
              ru.account_age_days AS rider_account_age_days,ru.average_rating AS rider_average_rating,
              ru.total_trips AS rider_total_trips,ru.synthetic AS rider_synthetic,
              du.archive_user_id AS driver_id,du.role AS driver_role,du.display_name AS driver_name,
              du.account_age_days AS driver_account_age_days,du.average_rating AS driver_average_rating,
              du.total_trips AS driver_total_trips,du.synthetic AS driver_synthetic
            FROM case_archive.archive_trip_snapshots t
            JOIN case_archive.archive_user_snapshots ru ON ru.archive_user_id=t.rider_archive_user_id
            JOIN case_archive.archive_user_snapshots du ON du.archive_user_id=t.driver_archive_user_id
            WHERE t.archive_ride_id=%s""",
            (row["archive_ride_id"],),
        ), row["archive_ride_id"])
        filer_row = _one(conn.execute(
            "SELECT * FROM case_archive.archive_user_snapshots WHERE archive_user_id=%s",
            (row["filing_archive_user_id"],),
        ), row["filing_archive_user_id"])
    decision = ArchiveDecision.model_validate(
        {
            "verdict": decision_row["verdict"],
            "ruling_type": decision_row["ruling_type"],
            "recommended_action_description": decision_row["recommended_action_description"],
            "recommended_amount": _money(decision_row["recommended_amount_cents"], decision_row["currency"]),
            "confidence": decision_row["confidence"],
            "decision_origin": decision_row["decision_origin"],
            "decided_at": as_utc(decision_row["decided_at"]),
            "synthetic": decision_row["synthetic"],
        }
    )
    review = HumanReview.model_validate(
        {
            "human_reviewed": review_row["human_reviewed"],
            "changed_fields": list(review_row["changed_fields"]),
            "reason_code": review_row["reason_code"],
            "rationale": review_row["rationale"],
            "agreed_with_agent": review_row["agreed_with_agent"],
            "reweighted_evidence": list(review_row["reweighted_evidence"]),
            "reviewed_at": as_utc(review_row["reviewed_at"]),
            "synthetic": review_row["synthetic"],
        }
    )
    case_payload = {key: value for key, value in row.items() if key != "monetary_impact_cents"}
    return ArchiveCase.model_validate(
        {
            **case_payload,
            "created_at": as_utc(row["created_at"]),
            "secondary_classifications": list(row["secondary_classifications"]),
            "monetary_impact": _money(row["monetary_impact_cents"], "SGD"),
            "evidence": [EvidenceReference.model_validate({**dict(r), "recorded_at": as_utc(r["recorded_at"])}) for r in evidence],
            "decision": decision,
            "human_review": review,
            "rulings": [_archive_ruling(dict(r)) for r in ruling_rows],
            "trip_snapshot": {
                "archive_ride_id": trip_row["archive_ride_id"],
                "trip_status": trip_row["trip_status"], "trip_at": as_utc(trip_row["trip_at"]),
                "requested_at": as_utc(trip_row["requested_at"]), "accepted_at": as_utc(trip_row["accepted_at"]),
                "pickup_at": as_utc(trip_row["pickup_at"]), "dropoff_at": as_utc(trip_row["dropoff_at"]),
                "service_tier": trip_row["service_tier"],
                "quoted_distance_meters": trip_row["quoted_distance_meters"],
                "quoted_duration_seconds": trip_row["quoted_duration_seconds"],
                "quoted_fare": _money(trip_row["quoted_fare_cents"], trip_row["currency"]) if trip_row["quoted_fare_cents"] is not None else None,
                "fare": _money(trip_row["fare_cents"], trip_row["currency"]) if trip_row["fare_cents"] is not None else None,
                "rider_rating": trip_row["rider_rating"], "driver_rating": trip_row["driver_rating"],
                "fare_breakdown": dict(trip_row["fare_breakdown"]),
                "pricing_structure": dict(trip_row["pricing_structure"]),
                "pickup_details": dict(trip_row["pickup_details"]),
                "dropoff_details": dict(trip_row["dropoff_details"]),
                "gps_data": list(trip_row["gps_data"]),
                "rider": {"archive_user_id":trip_row["rider_id"],"role":trip_row["rider_role"],
                    "display_name":trip_row["rider_name"],"account_age_days":trip_row["rider_account_age_days"],
                    "average_rating":trip_row["rider_average_rating"],"total_trips":trip_row["rider_total_trips"],
                    "synthetic":trip_row["rider_synthetic"]},
                "driver": {"archive_user_id":trip_row["driver_id"],"role":trip_row["driver_role"],
                    "display_name":trip_row["driver_name"],"account_age_days":trip_row["driver_account_age_days"],
                    "average_rating":trip_row["driver_average_rating"],"total_trips":trip_row["driver_total_trips"],
                    "synthetic":trip_row["driver_synthetic"]},
                "synthetic":trip_row["synthetic"],
            },
            "filing_user_snapshot": {"archive_user_id":filer_row["archive_user_id"],"role":filer_row["role"],
                "display_name":filer_row["display_name"],"account_age_days":filer_row["account_age_days"],
                "average_rating":filer_row["average_rating"],"total_trips":filer_row["total_trips"],
                "synthetic":filer_row["synthetic"]},
        }
    )


def search_archive(category: str, features: dict[str, Any], limit: int) -> list[ArchiveSearchResult]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    for key, value in features.items():
        if isinstance(value, str) and re.search(r"^DSP-\d+$|^RIDE-\d+$", value):
            raise ValueError(f"search_archive features must not contain live identifiers; got {key}={value!r}")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT p.archive_case_id, c.archive_ride_id, p.category, p.summary, p.policy_version,
                   p.feature_vector, p.synthetic, d.verdict, d.ruling_type,
                   d.recommended_action_description, d.recommended_amount_cents, d.currency,
                   d.confidence, d.decision_origin, d.decided_at, d.synthetic AS decision_synthetic
            FROM case_archive.archive_precedent_index p
            JOIN case_archive.archive_cases c USING (archive_case_id)
            JOIN case_archive.archive_case_decisions d USING (archive_case_id)
            WHERE p.category = %s
            ORDER BY CASE WHEN p.feature_vector @> %s::jsonb THEN 0 ELSE 1 END, p.archive_case_id
            LIMIT %s
            """,
            (category, psycopg.types.json.Jsonb(features), limit),
        ).fetchall()
        case_ids = [row["archive_case_id"] for row in rows]
        ruling_rows = conn.execute(
            """SELECT archive_case_id,ruling_stage,decision_origin,verdict,ruling_type,action_description,
              amount_cents,currency,confidence,decided_at,synthetic
            FROM case_archive.archive_case_rulings WHERE archive_case_id = ANY(%s)
            ORDER BY archive_case_id,CASE ruling_stage WHEN 'model_proposed' THEN 0 ELSE 1 END""",
            (case_ids,),
        ).fetchall() if case_ids else []
    rulings_by_case: dict[str, list[ArchiveRuling]] = {}
    for ruling_row in ruling_rows:
        ruling = dict(ruling_row)
        rulings_by_case.setdefault(ruling["archive_case_id"], []).append(_archive_ruling(ruling))
    return [
        ArchiveSearchResult.model_validate(
            {
                "archive_case_id": row["archive_case_id"],
                "archive_ride_id": row["archive_ride_id"],
                "category": row["category"],
                "summary": row["summary"],
                "policy_version": row["policy_version"],
                "feature_vector": dict(row["feature_vector"]),
                "decision": ArchiveDecision.model_validate(
                    {
                        "verdict": row["verdict"],
                        "ruling_type": row["ruling_type"],
                        "recommended_action_description": row["recommended_action_description"],
                        "recommended_amount": _money(row["recommended_amount_cents"], row["currency"]),
                        "confidence": row["confidence"],
                        "decision_origin": row["decision_origin"],
                        "decided_at": as_utc(row["decided_at"]),
                        "synthetic": row["decision_synthetic"],
                    }
                ),
                "rulings": rulings_by_case.get(row["archive_case_id"], []),
                "synthetic": row["synthetic"],
            }
        )
        for row in rows
    ]


def list_archive_disputes(limit: int | None = 200) -> list[ArchiveHistoryRecord]:
    """List archived disputes for the reviewer's read-only historical-case view."""
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000
    ):
        raise ValueError("limit must be between 1 and 1000")
    with _connect() as conn:
        query = """
            SELECT c.archive_case_id,c.archive_ride_id,c.category,c.subject,c.filed_by,
                   c.created_at,c.policy_version,c.synthetic,
                   d.verdict,d.ruling_type,d.recommended_action_description,
                   d.recommended_amount_cents,d.currency,d.confidence,d.decision_origin,
                   d.decided_at,d.synthetic AS decision_synthetic,h.human_reviewed
            FROM case_archive.archive_cases c
            JOIN case_archive.archive_case_decisions d USING (archive_case_id)
            JOIN case_archive.archive_human_reviews h USING (archive_case_id)
            ORDER BY c.created_at DESC,c.archive_case_id
            """
        if limit is None:
            rows = conn.execute(query).fetchall()
        else:
            rows = conn.execute(query + " LIMIT %s", (limit,)).fetchall()
        case_ids = [row["archive_case_id"] for row in rows]
        ruling_rows = conn.execute(
            """SELECT archive_case_id,ruling_stage,decision_origin,verdict,ruling_type,
                      action_description,amount_cents,currency,confidence,decided_at,synthetic
               FROM case_archive.archive_case_rulings
               WHERE archive_case_id = ANY(%s)
               ORDER BY archive_case_id,
                 CASE ruling_stage WHEN 'model_proposed' THEN 0 ELSE 1 END""",
            (case_ids,),
        ).fetchall() if case_ids else []
    rulings_by_case: dict[str, list[ArchiveRuling]] = {}
    for row in ruling_rows:
        ruling = dict(row)
        rulings_by_case.setdefault(ruling["archive_case_id"], []).append(_archive_ruling(ruling))
    return [
        ArchiveHistoryRecord.model_validate({
            "archive_case_id": row["archive_case_id"],
            "archive_ride_id": row["archive_ride_id"],
            "category": row["category"],
            "subject": row["subject"],
            "filed_by": row["filed_by"],
            "created_at": as_utc(row["created_at"]),
            "policy_version": row["policy_version"],
            "decision": ArchiveDecision.model_validate({
                "verdict": row["verdict"],
                "ruling_type": row["ruling_type"],
                "recommended_action_description": row["recommended_action_description"],
                "recommended_amount": _money(row["recommended_amount_cents"], row["currency"]),
                "confidence": row["confidence"],
                "decision_origin": row["decision_origin"],
                "decided_at": as_utc(row["decided_at"]),
                "synthetic": row["decision_synthetic"],
            }),
            "rulings": rulings_by_case.get(row["archive_case_id"], []),
            "human_reviewed": row["human_reviewed"],
            "synthetic": row["synthetic"],
        })
        for row in rows
    ]
