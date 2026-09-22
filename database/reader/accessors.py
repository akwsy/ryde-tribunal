from __future__ import annotations

import os
import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .models import (
    ArchiveCase,
    ArchiveDecision,
    ArchiveSearchResult,
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
    Route,
    Stop,
    Waypoint,
    as_utc,
)

DEFAULT_DATABASE_URL = "postgresql:///ryde_tribunal"


def _connect() -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL), row_factory=dict_row)


def _one(cur: psycopg.Cursor[dict[str, Any]], label: str) -> dict[str, Any]:
    row = cur.fetchone()
    if row is None:
        raise LookupError(f"{label} not found")
    return dict(row)


def _money(amount_cents: int, currency: str) -> Money:
    return Money.model_validate({"amount_cents": amount_cents, "currency": currency})


def get_ride(ride_id: str) -> RideHeader:
    with _connect() as conn:
        row = _one(
            conn.execute(
                """
                SELECT r.ride_id, r.rider_user_id, r.driver_user_id, r.requested_at, r.accepted_at,
                       r.pickup_at, r.dropoff_at, r.ride_status, r.service_tier,
                       r.quoted_distance_meters, r.quoted_duration_seconds, r.quoted_fare_cents,
                       r.currency, f.total_fare_cents, r.synthetic
                FROM ride_data.rides r
                JOIN ride_data.ride_fare_breakdowns f USING (ride_id)
                WHERE r.ride_id = %s
                """,
                (ride_id,),
            ),
            ride_id,
        )
    return RideHeader.model_validate(
        {
            "ride_id": row["ride_id"],
            "rider_user_id": row["rider_user_id"],
            "driver_user_id": row["driver_user_id"],
            "requested_at": as_utc(row["requested_at"]),
            "accepted_at": as_utc(row["accepted_at"]),
            "pickup_at": as_utc(row["pickup_at"]),
            "dropoff_at": as_utc(row["dropoff_at"]),
            "ride_status": row["ride_status"],
            "service_tier": row["service_tier"],
            "quoted_distance_meters": row["quoted_distance_meters"],
            "quoted_duration_seconds": row["quoted_duration_seconds"],
            "quoted_fare": _money(row["quoted_fare_cents"], row["currency"]),
            "fare_total": _money(row["total_fare_cents"], row["currency"]),
            "synthetic": row["synthetic"],
        }
    )


def get_route(ride_id: str) -> Route:
    with _connect() as conn:
        route = _one(
            conn.execute("SELECT * FROM ride_data.ride_route_plans WHERE ride_id = %s", (ride_id,)),
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
            "waypoints": [Waypoint.model_validate({**dict(row), "recorded_at": as_utc(row["recorded_at"])}) for row in waypoint_rows],
            "stops": [Stop.model_validate({**dict(row), "started_at": as_utc(row["started_at"]), "ended_at": as_utc(row["ended_at"])}) for row in stop_rows],
        }
    )


def get_gps_samples(ride_id: str) -> list[GpsSample]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sample_id, ride_id, sample_at, lat, lon, accuracy_meters, speed_meters_per_second, collector, synthetic FROM ride_data.ride_gps_samples WHERE ride_id = %s ORDER BY sample_at, sample_id",
            (ride_id,),
        ).fetchall()
    return [GpsSample.model_validate({**dict(row), "sample_at": as_utc(row["sample_at"])}) for row in rows]


def get_chat_log(ride_id: str) -> list[ChatMessage]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT message_id, ride_id, participant_role, sent_at, message_text, synthetic FROM ride_data.ride_chat_messages WHERE ride_id = %s ORDER BY sent_at, message_id",
            (ride_id,),
        ).fetchall()
    return [ChatMessage.model_validate({**dict(row), "sent_at": as_utc(row["sent_at"])}) for row in rows]


def get_fare_breakdown(ride_id: str) -> FareBreakdown:
    with _connect() as conn:
        row = _one(
            conn.execute("SELECT * FROM ride_data.ride_fare_breakdowns WHERE ride_id = %s", (ride_id,)),
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
            "base_fare": _money(row["base_fare_cents"], row["currency"]),
            "distance_fare": _money(row["distance_fare_cents"], row["currency"]),
            "time_fare": _money(row["time_fare_cents"], row["currency"]),
            "waiting_fare": _money(row["waiting_fare_cents"], row["currency"]),
            "surge_multiplier": row["surge_multiplier"],
            "surge_fare": _money(row["surge_fare_cents"], row["currency"]),
            "cancellation_fee": _money(row["cancellation_fee_cents"], row["currency"]),
            "platform_fee": _money(row["platform_fee_cents"], row["currency"]),
            "total_fare": _money(row["total_fare_cents"], row["currency"]),
            "adjustments": [
                FareAdjustment.model_validate({"adjustment_type": r["adjustment_type"], "amount": {"amount_cents": r["amount_cents"], "currency": r["currency"]}, "applied_at": as_utc(r["applied_at"]), "synthetic": r["synthetic"]})
                for r in adjustments
            ],
            "promos": [
                PromoApplication.model_validate({"promo_code": r["promo_code"], "amount": {"amount_cents": r["amount_cents"], "currency": r["currency"]}, "applied_at": as_utc(r["applied_at"]), "synthetic": r["synthetic"]})
                for r in promos
            ],
            "synthetic": row["synthetic"],
        }
    )


def get_profile(user_id: str) -> Profile:
    with _connect() as conn:
        row = _one(
            conn.execute(
                """
                SELECT u.user_id, u.role, u.display_handle, u.created_at, p.account_age_days,
                       p.lifetime_completed_rides, p.average_rating, p.rating_trend, p.synthetic
                FROM ride_data.users u
                JOIN ride_data.user_profiles p USING (user_id)
                WHERE u.user_id = %s
                """,
                (user_id,),
            ),
            user_id,
        )
        counters = _one(conn.execute("SELECT * FROM ride_data.user_dispute_counters WHERE user_id = %s", (user_id,)), user_id)
        ratings = conn.execute(
            "SELECT rating_at, rating, sample_size, synthetic FROM ride_data.user_rating_history WHERE user_id = %s ORDER BY rating_at",
            (user_id,),
        ).fetchall()
    return Profile.model_validate(
        {
            **row,
            "created_at": as_utc(row["created_at"]),
            "dispute_counts": DisputeCounters.model_validate({k: v for k, v in counters.items() if k != "user_id"}),
            "rating_history": [RatingPoint.model_validate({**dict(r), "rating_at": as_utc(r["rating_at"])}) for r in ratings],
            "prior_classifications": ["route_deviation"] * counters["route_deviation_count"] + ["no_show"] * counters["no_show_count"] + ["property_damage"] * counters["property_damage_count"] + ["safety_incident"] * counters["safety_incident_count"],
        }
    )


def get_archive_case(archive_case_id: str) -> ArchiveCase:
    if not re.fullmatch(r"^DSP-ARCH-\d{6}$", archive_case_id):
        raise ValueError(f"archive case id must match ^DSP-ARCH-\\d{{6}}$; got {archive_case_id!r}")
    with _connect() as conn:
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
            "SELECT archive_evidence_id AS evidence_id, evidence_class, source, recorded_at, visibility, synthetic FROM case_archive.archive_case_evidence WHERE archive_case_id = %s ORDER BY archive_evidence_id",
            (archive_case_id,),
        ).fetchall()
        decision_row = _one(conn.execute("SELECT * FROM case_archive.archive_case_decisions WHERE archive_case_id = %s", (archive_case_id,)), archive_case_id)
        review_row = _one(conn.execute("SELECT * FROM case_archive.archive_human_reviews WHERE archive_case_id = %s", (archive_case_id,)), archive_case_id)
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
                "synthetic": row["synthetic"],
            }
        )
        for row in rows
    ]
