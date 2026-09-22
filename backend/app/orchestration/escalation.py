"""Escalation and impact (RP-ESC-*, D-09/D-10/D-11, RP-SAFETY-001).

Escalation is applied to the Judge's ruling AFTER it is produced — it never precomputes the
ruling. It answers: does this ruling stand as an automated resolution, or must a human decide?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImpactInputs:
    category: str
    amount_cents: int
    fraud_risk: float
    party_disputes_30d: int
    safety_signal: bool


@dataclass(frozen=True)
class EscalationDecision:
    escalated: bool
    reasons: list[str]
    high_impact: bool


def assess_high_impact(inp: ImpactInputs, *, high_impact_amount_cents: int,
                       fraud_threshold: float) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if inp.amount_cents >= high_impact_amount_cents:
        reasons.append("monetary_high_impact")
    if inp.category == "safety_incident" or inp.safety_signal:
        reasons.append("safety")
    if inp.fraud_risk >= fraud_threshold:
        reasons.append("fraud_risk")
    if inp.party_disputes_30d >= 3:
        reasons.append("repeat_disputant")
    return (bool(reasons), reasons)


def decide_escalation(
    *,
    ruling_type: str,
    confidence: float,
    recommended_amount_cents: int,
    disputed_fare_component_cents: int,
    impact: ImpactInputs,
    confidence_threshold: float,
    high_impact_amount_cents: int,
    goodwill_cap_cents: int,
    fraud_threshold: float,
    insufficient: bool,
) -> EscalationDecision:
    reasons: list[str] = []

    # RP-SAFETY-001: any safety incident escalates regardless of confidence.
    if impact.category == "safety_incident" or impact.safety_signal:
        reasons.append("safety_incident")

    # RP-ESC-001 / D-09: below the confidence threshold.
    if confidence < confidence_threshold:
        reasons.append("confidence_below_threshold")

    # RP-ESC-002: material uncertainty / insufficiency / contradiction.
    if insufficient:
        reasons.append("insufficient_or_contradictory_evidence")

    # RP-ESC-003 / D-10: high impact.
    high, high_reasons = assess_high_impact(
        impact,
        high_impact_amount_cents=high_impact_amount_cents,
        fraud_threshold=fraud_threshold,
    )
    if high:
        reasons.append("high_impact")

    # RP-ESC-004 / D-11: remedy exceeds automated caps.
    if ruling_type == "refund" and recommended_amount_cents > disputed_fare_component_cents:
        reasons.append("exceeds_refund_cap")
    if ruling_type == "compensation" and recommended_amount_cents > goodwill_cap_cents:
        reasons.append("exceeds_goodwill_cap")

    # De-dup while preserving order.
    seen: set[str] = set()
    ordered = [r for r in reasons if not (r in seen or seen.add(r))]
    return EscalationDecision(escalated=bool(ordered), reasons=ordered, high_impact=high)


def human_review_summary(
    *,
    category: str,
    question: str,
    evidence_relied_on: list[str],
    conflict_or_gap: str,
    rider_argument: str,
    driver_argument: str,
    reasons: list[str],
) -> str:
    """RP-ESC-005: the complete summary a reviewer needs."""
    return (
        f"QUESTION TO DECIDE: {question}\n"
        f"CATEGORY: {category}\n"
        f"EVIDENCE RELIED ON: {', '.join(evidence_relied_on) or 'none'}\n"
        f"WHY ESCALATED: {', '.join(reasons) or 'n/a'} — {conflict_or_gap}\n"
        f"RIDER ARGUED: {rider_argument}\n"
        f"DRIVER ARGUED: {driver_argument}"
    )


def assess_fraud_risk(profile: dict[str, Any] | None) -> float:
    """Prior dispute history informs fraud assessment (RP-EV-004) but never by itself decides.
    A simple monotone signal from prior-dispute density; capped [0,1]."""
    if not profile:
        return 0.0
    d30 = int(profile.get("disputes_last_30d", 0) or 0)
    total = int(profile.get("disputes_total", 0) or 0)
    risk = min(0.2 * d30 + 0.02 * total, 1.0)
    return round(risk, 3)


class RulingIntegrityError(ValueError):
    """A refund/compensation ruling was constructed without a positive monetary amount — a
    remedy with no figure. Structurally rejected so it can never be returned."""


# Ruling types that MUST carry a positive monetary amount.
_MONETARY_RULINGS = {"refund", "compensation"}


def finalize_ruling(judge_out: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Enforce ruling integrity at the point the ruling is finalized (point 1): a `refund` or
    `compensation` MUST carry a non-null, positive `amount`. This applies to EVERY category.

    Returns (possibly-rewritten judge_out, downgraded?). If a monetary ruling has no positive
    amount, it is NOT returned as a refund: it is downgraded to `no_action` and the caller is
    told (via the returned flag) to treat the case as insufficient and escalate — a policy
    breach with no remedy to grant is a case for a human, not a figureless refund.

    A monetary ruling that somehow still carries no amount after this raises
    RulingIntegrityError rather than emitting a remedy without a figure.
    """
    out = dict(judge_out)
    ruling_type = out.get("ruling_type")
    action = out.get("recommended_action") or {}
    amount = (action.get("amount") or {}).get("amount_cents")

    if ruling_type in _MONETARY_RULINGS:
        if amount is None or int(amount) <= 0:
            # Downgrade: a refund/compensation without a positive figure is not a valid remedy.
            out["ruling_type"] = "no_action"
            out["recommended_action"] = {
                "description": (
                    "Policy breach established but the computed remedy is zero (nothing to "
                    "refund/compensate); no monetary remedy is granted."
                )
            }
            out.pop("_amount", None)
            return out, True
    return out, False


def assert_ruling_integrity(judge_out: dict[str, Any]) -> None:
    """Hard invariant for tests + a last-line assertion: a monetary ruling in the FINAL payload
    must carry a positive amount, or RulingIntegrityError is raised."""
    ruling_type = judge_out.get("ruling_type")
    amount = ((judge_out.get("recommended_action") or {}).get("amount") or {}).get("amount_cents")
    if ruling_type in _MONETARY_RULINGS and (amount is None or int(amount) <= 0):
        raise RulingIntegrityError(
            f"{ruling_type} ruling has no positive amount ({amount!r})"
        )
