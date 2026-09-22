"""The database read contract (docs/02-api-contract.md §5).

The backend reads through EIGHT documented, READ-ONLY accessors ONLY. The database specialist
implements them against Postgres; that implementation does not exist yet, so this module
defines the interface (a Protocol), the raw record shapes, and the archive-id guard the
backend must apply on its own side. Everything downstream depends on this interface, never on
a concrete reader.

Integrity rule I-2 (owned by the database, honoured here): live accessors return NO outcome
fields. There is NO live-case accessor — the live case lives in the backend's `tribunal`
schema. `search_archive` / `get_archive_case` are the ONLY source of verdicts, advisory, and
confined to the `DSP-ARCH-*` / `RIDE-ARCH-*` namespace. Integrity rule I-2a: an archive
accessor RAISES on a live `DSP-*` / `RIDE-*` id — see `assert_archive_id` below.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

# I-2a: archive accessors accept ONLY archive-namespaced ids and raise on a live id.
_ARCHIVE_ID_RE = re.compile(r"^(DSP-ARCH|RIDE-ARCH)-\d+$")
_LIVE_ID_RE = re.compile(r"^(DSP|RIDE)-\d+$")


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
    """The eight READ-ONLY accessors (docs/02-api-contract.md §5). There is no write surface:
    the data the tribunal reasons over cannot be mutated by the thing doing the reasoning
    (I-2). There is NO accessor for the live case — it lives in the backend-owned `tribunal`
    schema (see `app/persistence/store.py`). The two archive accessors (`search_archive`,
    `get_archive_case`) are the only source of verdicts, both advisory and both confined to
    the `DSP-ARCH-*` / `RIDE-ARCH-*` namespace; `get_archive_case` RAISES on a live id (I-2a).
    All may raise DatabaseUnavailable."""

    def get_ride(self, ride_id: str) -> RideRecord | None: ...
    def get_route(self, ride_id: str) -> RouteRecord | None: ...
    def get_gps_samples(self, ride_id: str) -> GpsSamples | None: ...
    def get_chat_log(self, ride_id: str) -> ChatLog | None: ...
    def get_fare_breakdown(self, ride_id: str) -> FareBreakdown | None: ...
    def get_profile(self, user_id: str) -> Profile | None: ...
    def search_archive(
        self, category: str, features: dict[str, Any], limit: int
    ) -> list[ArchiveCase]: ...
    def get_archive_case(self, archive_case_id: str) -> ArchiveCase | None: ...


class DatabaseUnavailable(RuntimeError):
    """Raised by a reader when the datastore cannot be reached. Maps to `database_unavailable`
    and NEVER to a ruling (contract §1, brief §7)."""


class LiveIdRejected(ValueError):
    """Raised when a live `DSP-*` / `RIDE-*` id is routed to an archive accessor (I-2a). The
    case under adjudication must never look up its own answer through the archive."""


def assert_archive_id(identifier: str) -> str:
    """I-2a guard: accept only an archive-namespaced id (`DSP-ARCH-*` / `RIDE-ARCH-*`), and
    RAISE on a live id (or any other shape). Every archive accessor calls this before touching
    the store, so the guard lives on the backend side too — not only in the (not-yet-existing)
    database reader."""
    if _LIVE_ID_RE.match(identifier):
        raise LiveIdRejected(
            f"live id {identifier!r} routed to an archive accessor — the case cannot look up "
            f"its own answer (I-2a)"
        )
    if not _ARCHIVE_ID_RE.match(identifier):
        raise LiveIdRejected(
            f"{identifier!r} is not an archive id ({_ARCHIVE_ID_RE.pattern}) (I-2a)"
        )
    return identifier
