from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    @field_validator("synthetic", check_fields=False)
    @classmethod
    def _synthetic_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("database Phase Zero rows must be synthetic")
        return value


class Money(StrictModel):
    amount_cents: int = Field(ge=0)
    currency: Literal["SGD"]


class RideHeader(StrictModel):
    ride_id: str
    rider_user_id: str
    driver_user_id: str
    requested_at: datetime
    accepted_at: datetime | None
    pickup_at: datetime | None
    dropoff_at: datetime | None
    ride_status: str
    service_tier: str
    quoted_distance_meters: int
    quoted_duration_seconds: int
    quoted_fare: Money
    fare_total: Money
    synthetic: bool


class Waypoint(StrictModel):
    route_kind: Literal["planned", "actual"]
    sequence_no: int
    lat: Decimal
    lon: Decimal
    label: str
    recorded_at: datetime | None
    synthetic: bool


class Stop(StrictModel):
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    lat: Decimal
    lon: Decimal
    rider_requested: bool
    note: str
    synthetic: bool


class Route(StrictModel):
    ride_id: str
    pickup_label: str
    pickup_lat: Decimal
    pickup_lon: Decimal
    dropoff_label: str
    dropoff_lat: Decimal
    dropoff_lon: Decimal
    planned_distance_meters: int
    actual_distance_meters: int
    planned_duration_seconds: int
    actual_duration_seconds: int
    driver_arrival_distance_meters: int | None
    driver_wait_seconds: int | None
    waypoints: list[Waypoint]
    stops: list[Stop]
    synthetic: bool


class GpsSample(StrictModel):
    sample_id: int
    ride_id: str
    sample_at: datetime
    lat: Decimal
    lon: Decimal
    accuracy_meters: Decimal
    speed_meters_per_second: Decimal
    collector: str
    synthetic: bool


class ChatMessage(StrictModel):
    message_id: str
    ride_id: str
    participant_role: Literal["rider", "driver", "support"]
    sent_at: datetime
    message_text: str
    synthetic: bool


class FareAdjustment(StrictModel):
    adjustment_type: str
    amount: Money
    applied_at: datetime
    synthetic: bool


class PromoApplication(StrictModel):
    promo_code: str
    amount: Money
    applied_at: datetime
    synthetic: bool


class FareBreakdown(StrictModel):
    ride_id: str
    base_fare: Money
    distance_fare: Money
    time_fare: Money
    waiting_fare: Money
    surge_multiplier: Decimal
    surge_fare: Money
    cancellation_fee: Money
    platform_fee: Money
    total_fare: Money
    adjustments: list[FareAdjustment]
    promos: list[PromoApplication]
    synthetic: bool


class RatingPoint(StrictModel):
    rating_at: datetime
    rating: Decimal
    sample_size: int
    synthetic: bool


class DisputeCounters(StrictModel):
    disputes_30d: int
    disputes_180d: int
    route_deviation_count: int
    no_show_count: int
    property_damage_count: int
    safety_incident_count: int
    synthetic: bool


class Profile(StrictModel):
    user_id: str
    role: Literal["rider", "driver"]
    display_handle: str
    created_at: datetime
    account_age_days: int
    lifetime_completed_rides: int
    average_rating: Decimal
    rating_trend: str
    dispute_counts: DisputeCounters
    rating_history: list[RatingPoint]
    prior_classifications: list[str]
    synthetic: bool


class EvidenceReference(StrictModel):
    evidence_id: str
    evidence_class: str
    source: str
    recorded_at: datetime
    visibility: str
    synthetic: bool


class ArchiveDecision(StrictModel):
    verdict: str
    ruling_type: str
    recommended_action_description: str
    recommended_amount: Money
    confidence: Decimal | None
    decision_origin: Literal["agent", "human"]
    decided_at: datetime
    synthetic: bool


class HumanReview(StrictModel):
    human_reviewed: bool
    changed_fields: list[str]
    reason_code: str | None
    rationale: str
    agreed_with_agent: bool | None
    reweighted_evidence: list[str]
    reviewed_at: datetime | None
    synthetic: bool


class ArchiveCase(StrictModel):
    archive_case_id: str
    archive_ride_id: str
    category: str
    subject: str
    filed_by: Literal["rider", "driver"]
    created_at: datetime
    policy_version: str
    primary_classification: str
    secondary_classifications: list[str]
    monetary_impact: Money
    fraud_risk: Decimal
    evidence: list[EvidenceReference]
    decision: ArchiveDecision
    human_review: HumanReview
    synthetic: bool


class ArchiveSearchResult(StrictModel):
    archive_case_id: str
    archive_ride_id: str
    category: str
    summary: str
    policy_version: str
    feature_vector: dict[str, Any]
    decision: ArchiveDecision
    synthetic: bool


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
