"""The database read contract.

The backend reads through eleven READ-ONLY accessors. This module defines the
interface (a Protocol), raw record shapes, and the archive-id guard the backend applies on its
own side. Everything downstream depends on this interface, never on a concrete reader.

Integrity rule I-2 (owned by the database, honoured here): live accessors return NO outcome
fields. There is NO live-case accessor — the live case lives in the backend's `tribunal`
schema. Live and archived disputes share the `DSP-######` shape; archive reads remain scoped
to archive-table accessors. Callers must use the explicit case source when routing a lookup.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

# I-2a: archive accessors validate canonical DSP IDs and remain archive-table-scoped.
_CASE_ID_RE = re.compile(r"^DSP-\d{6}$")


class _Raw(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")


class RideRecord(_Raw):
    ride_id: str  # RIDE-######; source is determined by accessor/table, not ID prefix
    rider_id: str  # USR-R-######
    driver_id: str  # USR-D-######
    booked_at: str | None = None
    completed_at: str | None = None
    status: str | None = None
    # Fare header — figures only, no outcome.
    quoted_fare_cents: int | None = None
    charged_fare_cents: int | None = None
    currency: str = "SGD"
    # Estimates offered at booking.
    planned_distance_km: float | None = None
    estimated_duration_s: int | None = None
    synthetic: bool = True
    company_trip_id: str | None = None
    source_system: str | None = None
    scheduled_at: str | None = None
    cancellation_timestamp: str | None = None
    cancellation_reason: str | None = None
    verification_status: str | None = None
    evidence_source: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    provenance: dict[str, Any] = {}


class RouteRecord(_Raw):
    ride_id: str
    pickup_label: str | None = None
    pickup_lat: float | None = None
    pickup_lon: float | None = None
    dropoff_label: str | None = None
    dropoff_lat: float | None = None
    dropoff_lon: float | None = None
    planned_distance_km: float | None = None
    actual_distance_km: float | None = None
    planned_duration_s: int | None = None
    actual_duration_s: int | None = None
    driver_arrival_distance_m: int | None = None
    driver_wait_seconds: int | None = None
    driver_arrival_at: str | None = None
    driver_wait_start_at: str | None = None
    waypoints: list[dict[str, Any]] = []
    stops: list[dict[str, Any]] = []  # each: {lat,lon,started_at,ended_at,duration_s,rider_requested}
    rider_requested_change: bool = False
    diversion_evidenced: bool = False
    source_system: str | None = None
    verification_status: str | None = None
    evidence_source: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    provenance: dict[str, Any] = {}


class GpsSample(_Raw):
    seq: int
    sequence_no: int | None = None
    lat: float
    lon: float
    at: str
    accuracy_m: float | None = None
    accuracy_meters: float | None = None
    sample_id: int | None = None
    status: str | None = None
    speed_kmh: float | None = None
    speed_meters_per_second: float | None = None
    collector: str | None = None
    source_system: str | None = None
    evidence_source: str | None = None
    verification_status: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    provenance: dict[str, Any] = {}


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
    message_id: str | None = None
    event_type: str | None = None
    message_type: str | None = None
    status: str | None = None
    source_system: str | None = None
    evidence_source: str | None = None
    verification_status: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    provenance: dict[str, Any] = {}


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
    surge_multiplier: float | None = None
    surge_applied_after_booking: bool | None = None
    promo_code: str | None = None
    promo_applied: bool | None = None
    promo_expected_cents: int | None = None
    cancellation_fee_cents: int | None = None
    platform_fee_cents: int | None = None
    total_fare_cents: int | None = None
    promos: list[dict[str, Any]] = []
    adjustments: list[FareComponent] = []
    verification_status: str | None = None
    evidence_source: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    provenance: dict[str, Any] = {}


class Profile(_Raw):
    user_id: str  # USR-R-###### or USR-D-######
    account_age_days: int | None = None
    avg_rating: float | None = None
    role: str | None = None
    display_handle: str | None = None
    created_at: str | None = None
    lifetime_completed_rides: int | None = None
    rating_trend: str | None = None
    fraud_flag_count: int | None = None
    fraud_flag_details: str | None = None
    company_dispute_history: Any = None
    disputes_total: int | None = None
    disputes_last_30d: int | None = None
    prior_classifications: list[str] = []
    company_user_id: str | None = None  # retained as supplied; never used as the app ID
    source_system: str | None = None
    full_name: str | None = None
    total_trips: int | None = None
    fraud_count: int | None = None
    fraud_details: Any = None
    source_dispute_history: Any = None
    payment_method: str | None = None
    vehicle: Any = None
    verification_status: str | None = None
    evidence_source: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
    provenance: dict[str, Any] = {}


class AppEvent(_Raw):
    event_id: str
    ride_id: str
    sequence_no: int
    event_at: str
    event_type: str
    details: str
    source_system: str | None = None
    evidence_source: str | None = None
    verification_status: str = "unverified"
    verified_by: str | None = None
    verified_at: str | None = None
    provenance: dict[str, Any] = {}
    synthetic: bool = True


class EvidenceRef(_Raw):
    evidence_id: str  # EV-######
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
    case_id: str  # DSP-######
    ride_id: str  # RIDE-######
    category: str
    filed_by: str
    subject: str
    description: str
    claimed_amount_cents: int | None = None
    currency: str = "SGD"
    category_details: dict[str, Any] = {}
    attachment_files: dict[str, dict[str, Any]] = {}
    filed_at: str = ""
    evidence: list[EvidenceRef] = []
    # For appeals (I-7): late/appended evidence carried on the case.
    is_appeal: bool = False


class ArchiveCase(_Raw):
    """Advisory precedent from archive_* (I-2), identified by its canonical DSP case ID."""

    archive_case_id: str  # DSP-######; source is archive table, not ID prefix
    archive_ride_id: str | None = None  # RIDE-######
    category: str
    ruling_type: str
    recommended_action: str
    confidence: float
    decision_origin: str  # human | agent
    policy_version: str
    features: dict[str, Any] = {}
    was_overridden: bool = False
    # Preserve the archive's proposal and any human-approved ruling as separate examples.
    rulings: list[dict[str, Any]] = []
    # Full archive-table row and snapshots, retained for read-only historical detail views.
    archive_record: dict[str, Any] = {}


class ArchiveHistoryRecord(_Raw):
    """One prior dispute with its effective and stage-specific historical rulings."""

    archive_case_id: str  # DSP-######; archive table supplies the source
    archive_ride_id: str  # RIDE-######; archive table supplies the source
    category: str
    subject: str
    filed_by: str
    created_at: str
    policy_version: str
    verdict: str
    ruling_type: str
    recommended_action: str
    amount_cents: int
    currency: str
    confidence: float | None = None
    decision_origin: str
    human_reviewed: bool
    rulings: list[dict[str, Any]] = []
    synthetic: bool = True


@runtime_checkable
class DatabaseReader(Protocol):
    """The eleven READ-ONLY accessors. There is no write surface:
    the data the tribunal reasons over cannot be mutated by the thing doing the reasoning
    (I-2). There is NO accessor for the live case — it lives in the backend-owned `tribunal`
    schema (see `app/persistence/store.py`). The archive accessors (`search_archive`,
    `get_archive_case`, `list_archive_disputes`) are strictly archive-table-scoped. Since
    archive and live cases now share `DSP-######`, callers must route using `case_source`;
    archive lookups must never fall through to the live store (I-2a).
    All may raise DatabaseUnavailable."""

    def get_ride(self, ride_id: str) -> RideRecord | None: ...
    def get_route(self, ride_id: str) -> RouteRecord | None: ...
    def get_gps_samples(self, ride_id: str) -> GpsSamples | None: ...
    def get_chat_log(self, ride_id: str) -> ChatLog | None: ...
    def get_app_events(self, ride_id: str) -> list[AppEvent]: ...
    def get_fare_breakdown(self, ride_id: str) -> FareBreakdown | None: ...
    def get_profile(self, user_id: str) -> Profile | None: ...
    def search_rides(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]: ...
    def search_archive(
        self, category: str, features: dict[str, Any], limit: int
    ) -> list[ArchiveCase]: ...
    def get_archive_case(self, archive_case_id: str) -> ArchiveCase | None: ...
    def list_archive_disputes(
        self, limit: int | None = 200
    ) -> list[ArchiveHistoryRecord]: ...


class DatabaseUnavailable(RuntimeError):
    """Raised by a reader when the datastore cannot be reached. Maps to `database_unavailable`
    and NEVER to a ruling (contract §1, brief §7)."""


class LiveIdRejected(ValueError):
    """Raised when a malformed or explicitly live ID is routed as an archive ID (I-2a).

    Canonical DSP IDs cannot encode their source. Archive accessors are kept archive-only at
    the persistence boundary, and adjudication uses search results rather than routing the
    active case ID through this accessor.
    """


def assert_archive_id(identifier: str) -> str:
    """Validate canonical shape before an archive-table-only lookup.

    Source cannot be inferred from the ID after the global sequence migration. This guard
    therefore validates shape only; the underlying archive accessor must remain strictly
    scoped to archive records and must not fall back to the live tribunal store.
    """
    if not _CASE_ID_RE.fullmatch(identifier):
        raise LiveIdRejected(f"{identifier!r} is not a canonical DSP case ID (I-2a)")
    return identifier
