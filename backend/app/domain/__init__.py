"""Core domain vocabulary: enums and immutable value types shared across the service.

These mirror docs/02-api-contract.md exactly. Money is integer cents + currency, never a
float (contract §1).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DisputeCategory(str, Enum):
    route_deviation = "route_deviation"
    no_show = "no_show"
    property_damage = "property_damage"  # schema-supported, Phase One adjudication (D-14)
    safety_incident = "safety_incident"  # schema-supported, Phase One adjudication (D-14)


# Categories this phase adjudicates end to end (D-14).
PHASE_ZERO_CATEGORIES = frozenset({DisputeCategory.route_deviation, DisputeCategory.no_show})


class FiledBy(str, Enum):
    rider = "rider"
    driver = "driver"


class CaseStatus(str, Enum):
    queued = "queued"
    resolved = "resolved"
    escalated = "escalated"
    pending_review = "pending_review"
    overridden = "overridden"


class RulingType(str, Enum):
    refund = "refund"
    compensation = "compensation"
    no_action = "no_action"


class VerificationStatus(str, Enum):
    verified = "verified"
    unverified = "unverified"
    disputed = "disputed"
    unverifiable = "unverifiable"


class Visibility(str, Enum):
    both = "both"
    rider_only = "rider_only"
    driver_only = "driver_only"
    reviewer_only = "reviewer_only"


class EvidenceClass(str, Enum):
    gps_telemetry = "gps_telemetry"
    chat_log = "chat_log"
    fare = "fare"
    profile_history = "profile_history"
    attachment = "attachment"
    external = "external"


class EvidenceSource(str, Enum):
    system_record = "system_record"
    rider_submitted = "rider_submitted"
    driver_submitted = "driver_submitted"
    external = "external"


# Closed override reason vocabulary (contract §2 POST /override).
OVERRIDE_REASON_CODES = frozenset(
    {
        "policy_misapplied",
        "evidence_misweighted",
        "evidence_missing",
        "fraud_suspected",
        "goodwill",
        "safety_override",
        "other",
    }
)


class Money(BaseModel):
    """Integer cents plus a currency code — never a float (contract §1)."""

    model_config = ConfigDict(frozen=True)

    amount_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


# Which actor role may see evidence of a given visibility. Advocates are restricted to
# what their party may see (I-3 check 5, ASSUMPTIONS A-3).
def visible_to(visibility: Visibility, actor: FiledBy | str) -> bool:
    actor_val = actor.value if isinstance(actor, FiledBy) else actor
    if visibility == Visibility.both:
        return True
    if visibility == Visibility.reviewer_only:
        return actor_val == "reviewer"
    if visibility == Visibility.rider_only:
        return actor_val == "rider"
    if visibility == Visibility.driver_only:
        return actor_val == "driver"
    return False
