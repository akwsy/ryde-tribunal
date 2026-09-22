"""The database read contract (docs/02-api-contract.md §5).

The backend reads through nine documented accessors ONLY. The database specialist implements
them against Postgres; that implementation does not exist yet, so this module defines the
interface (a Protocol) and the raw record shapes the accessors return. Everything downstream
depends on this interface, never on a concrete reader.

Integrity rule I-2 (owned by the database, honoured here): live accessors return NO outcome
fields. These record shapes deliberately carry no verdict/fault/expected-result/ground-truth
field, and `search_archive` — the ONLY source of verdicts — returns disjoint-namespace ids
and is advisory.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class _Raw(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")


class RideRecord(_Raw):
    ride_id: str
    rider_id: str
    driver_id: str
    booked_at: str
    completed_at: str | None = None
    status: str
    # Fare header — figures only, no outcome.
    quoted_fare_cents: int
    charged_fare_cents: int
    currency: str = "SGD"
    # Estimates offered at booking.
    planned_distance_km: float | None = None
    estimated_duration_s: int | None = None


class RouteRecord(_Raw):
    ride_id: str
    planned_distance_km: float
    actual_distance_km: float
    planned_duration_s: int
    actual_duration_s: int
    waypoints: list[dict[str, Any]] = []
    stops: list[dict[str, Any]] = []  # each: {lat,lon,started_at,ended_at,duration_s,rider_requested}
    rider_requested_change: bool = False
    diversion_evidenced: bool = False


class GpsSample(_Raw):
    seq: int
    lat: float
    lon: float
    at: str
    accuracy_m: float


class GpsSamples(_Raw):
    ride_id: str
    samples: list[GpsSample] = []
    # Pickup point declared at booking, for no-show arrival checks.
    pickup_lat: float | None = None
    pickup_lon: float | None = None
    min_distance_to_pickup_m: float | None = None


class ChatMessage(_Raw):
    seq: int
    role: str  # rider | driver | system
    at: str
    text: str
    kind: str = "message"  # message | call_attempt


class ChatLog(_Raw):
    ride_id: str
    messages: list[ChatMessage] = []


class FareComponent(_Raw):
    name: str
    amount_cents: int


class FareBreakdown(_Raw):
    ride_id: str
    currency: str = "SGD"
    components: list[FareComponent] = []
    surge_multiplier: float = 1.0
    surge_applied_after_booking: bool = False
    promo_code: str | None = None
    promo_applied: bool = True
    promo_expected_cents: int = 0
    cancellation_fee_cents: int = 0
    adjustments: list[FareComponent] = []


class Profile(_Raw):
    user_id: str
    account_age_days: int
    avg_rating: float | None = None
    disputes_total: int = 0
    disputes_last_30d: int = 0
    prior_classifications: list[str] = []


class EvidenceRef(_Raw):
    evidence_id: str
    class_: str  # aliased below
    source: str
    visibility: str = "both"
    verification_status: str = "verified"
    verification_method: str = ""
    verification_uncertainty_pct: float = 0.0
    recorded_at: str = ""
    provenance: dict[str, Any] = {}
    payload: dict[str, Any] = {}


class CaseRecord(_Raw):
    case_id: str
    ride_id: str
    category: str
    filed_by: str
    subject: str
    description: str
    claimed_amount_cents: int | None = None
    currency: str = "SGD"
    filed_at: str = ""
    evidence: list[EvidenceRef] = []
    # For appeals (I-7): late/appended evidence carried on the case.
    is_appeal: bool = False


class ArchiveCase(_Raw):
    """Advisory precedent from archive_* (I-2). Disjoint id namespace: DSP-ARCH-*, RIDE-ARCH-*."""

    archive_case_id: str  # DSP-ARCH-*
    category: str
    ruling_type: str
    recommended_action: str
    confidence: float
    decision_origin: str  # human | agent
    policy_version: str
    features: dict[str, Any] = {}
    was_overridden: bool = False


@runtime_checkable
class DatabaseReader(Protocol):
    """The nine accessors (docs/02-api-contract.md §5). All may raise DatabaseUnavailable."""

    def get_ride(self, ride_id: str) -> RideRecord | None: ...
    def get_route(self, ride_id: str) -> RouteRecord | None: ...
    def get_gps_samples(self, ride_id: str) -> GpsSamples | None: ...
    def get_chat_log(self, ride_id: str) -> ChatLog | None: ...
    def get_fare_breakdown(self, ride_id: str) -> FareBreakdown | None: ...
    def get_profile(self, user_id: str) -> Profile | None: ...
    def get_case(self, case_id: str) -> CaseRecord | None: ...
    def search_archive(
        self, category: str, features: dict[str, Any], limit: int
    ) -> list[ArchiveCase]: ...
    def persist_model_work(self, case_id: str, payload: dict[str, Any]) -> None: ...


class DatabaseUnavailable(RuntimeError):
    """Raised by a reader when the datastore cannot be reached. Maps to `database_unavailable`
    and NEVER to a ruling (contract §1, brief §7)."""
