from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Money(StrictModel):
    amount_cents: int = Field(ge=0)
    currency: Literal["SGD"]


VerificationStatus = Literal["verified", "unverified", "disputed", "unverifiable"]


class EvidenceProvenance(StrictModel):
    source_system: str | None = None
    evidence_source: str | None = None
    verification_status: VerificationStatus = "unverified"
    verified_by: str | None = None
    verified_at: datetime | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class RideHeader(EvidenceProvenance):
    ride_id: str
    company_trip_id: str | None = None
    rider_user_id: str
    driver_user_id: str
    requested_at: datetime | None
    scheduled_at: datetime | None = None
    accepted_at: datetime | None
    pickup_at: datetime | None
    dropoff_at: datetime | None
    cancellation_at: datetime | None = None
    cancellation_reason: str | None = None
    ride_status: str | None
    service_tier: str | None
    quoted_distance_meters: int | None
    quoted_duration_seconds: int | None
    quoted_fare: Money | None
    fare_total: Money | None
    cancellation_fee: Money | None = None
    synthetic: bool


class RideSearchResult(StrictModel):
    """Minimal trip details for selecting an existing ride when filing a dispute."""

    ride_id: str
    company_trip_id: str | None = None
    source_system: str | None = None
    booked_at: datetime | None
    ride_status: str | None
    pickup_label: str | None
    dropoff_label: str | None
    rider_name: str | None
    driver_name: str | None


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


class Route(EvidenceProvenance):
    ride_id: str
    pickup_label: str
    pickup_lat: Decimal
    pickup_lon: Decimal
    dropoff_label: str
    dropoff_lat: Decimal
    dropoff_lon: Decimal
    planned_distance_meters: int | None
    actual_distance_meters: int | None
    planned_duration_seconds: int | None
    actual_duration_seconds: int | None
    driver_arrival_distance_meters: int | None
    driver_wait_seconds: int | None
    driver_arrival_at: datetime | None = None
    driver_wait_start_at: datetime | None = None
    waypoints: list[Waypoint]
    stops: list[Stop]
    synthetic: bool


class GpsSample(EvidenceProvenance):
    sample_id: int
    ride_id: str
    sample_at: datetime
    sequence_no: int | None = None
    lat: Decimal
    lon: Decimal
    accuracy_meters: Decimal | None
    speed_meters_per_second: Decimal | None
    speed_kmh: Decimal | None = None
    status: str | None = None
    collector: str | None
    synthetic: bool


class ChatMessage(EvidenceProvenance):
    message_id: str
    ride_id: str
    participant_role: Literal["rider", "driver", "support", "system"]
    sent_at: datetime
    message_text: str
    sequence_no: int | None = None
    message_type: str = "message"
    synthetic: bool


class AppEvent(EvidenceProvenance):
    event_id: str
    ride_id: str
    sequence_no: int
    event_at: datetime
    event_type: str
    details: str
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


class FareBreakdown(EvidenceProvenance):
    ride_id: str
    base_fare: Money | None
    distance_fare: Money | None
    time_fare: Money | None
    waiting_fare: Money | None
    surge_multiplier: Decimal | None
    surge_fare: Money | None
    cancellation_fee: Money | None
    platform_fee: Money | None
    total_fare: Money | None
    adjustments: list[FareAdjustment]
    promos: list[PromoApplication]
    synthetic: bool


class RatingPoint(StrictModel):
    rating_at: datetime
    rating: Decimal
    sample_size: int
    synthetic: bool


class DisputeCounters(StrictModel):
    disputes_30d: int | None
    disputes_180d: int | None
    route_deviation_count: int | None
    no_show_count: int | None
    property_damage_count: int | None
    safety_incident_count: int | None
    synthetic: bool


class CompanyDisputeHistory(StrictModel):
    total: int | None
    upheld: int | None
    rejected: int | None
    upheld_against: int | None


class Profile(EvidenceProvenance):
    user_id: str
    company_user_id: str | None = None
    role: Literal["rider", "driver"]
    display_handle: str | None
    full_name: str | None = None
    created_at: datetime | None
    account_age_days: int
    lifetime_completed_rides: int | None
    total_trips: int | None = None
    average_rating: Decimal
    rating_trend: str | None
    company_dispute_history: CompanyDisputeHistory | None = None
    fraud_flag_count: int | None = None
    fraud_flag_details: str | None = None
    payment_method: str | None = None
    vehicle: str | None = None
    dispute_counts: DisputeCounters | None
    rating_history: list[RatingPoint]
    prior_classifications: list[str] | None
    synthetic: bool


class EvidenceReference(StrictModel):
    evidence_id: str
    evidence_class: str
    source: str
    recorded_at: datetime
    visibility: str
    provenance: dict[str, Any]
    verification: dict[str, Any]
    payload: dict[str, Any]
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


class ArchiveRuling(StrictModel):
    stage: Literal["model_proposed", "reviewer_approved"]
    decision: ArchiveDecision


class ArchiveUserSnapshot(StrictModel):
    archive_user_id: str
    role: Literal["rider", "driver"]
    display_name: str
    account_age_days: int
    average_rating: Decimal | None
    total_trips: int | None
    synthetic: bool


class ArchiveTripSnapshot(StrictModel):
    archive_ride_id: str
    trip_status: str
    trip_at: datetime
    requested_at: datetime
    accepted_at: datetime | None
    pickup_at: datetime | None
    dropoff_at: datetime | None
    service_tier: str
    quoted_distance_meters: int | None
    quoted_duration_seconds: int | None
    quoted_fare: Money | None
    fare: Money | None
    rider_rating: Decimal | None
    driver_rating: Decimal | None
    fare_breakdown: dict[str, Any]
    pricing_structure: dict[str, Any]
    pickup_details: dict[str, Any]
    dropoff_details: dict[str, Any]
    gps_data: list[dict[str, Any]]
    rider: ArchiveUserSnapshot
    driver: ArchiveUserSnapshot
    synthetic: bool


class ArchiveCase(StrictModel):
    archive_case_id: str
    archive_ride_id: str
    # Import/provenance columns selected from case_archive.archive_cases. The filing user
    # also appears as a snapshot below; retaining its FK here preserves the source row shape.
    filing_archive_user_id: str
    bundle_case_key: str | None = None
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
    rulings: list[ArchiveRuling]
    trip_snapshot: ArchiveTripSnapshot
    filing_user_snapshot: ArchiveUserSnapshot
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
    rulings: list[ArchiveRuling]
    synthetic: bool


class ArchiveHistoryRecord(StrictModel):
    """Outcome-bearing summary for the reviewer-facing historical archive list."""

    archive_case_id: str
    archive_ride_id: str
    category: str
    subject: str
    filed_by: Literal["rider", "driver"]
    created_at: datetime
    policy_version: str
    decision: ArchiveDecision
    rulings: list[ArchiveRuling]
    human_reviewed: bool
    synthetic: bool


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
