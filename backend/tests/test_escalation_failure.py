"""Failure and escalation (brief §7).

  * Contradictory or missing evidence → uncertain or escalated, never a confident ruling.
  * High-impact case → escalated with a complete human-review summary (RP-ESC-005).
  * A safety signal is escalated regardless of confidence (RP-SAFETY-001/002).
  * A malformed evidence record surfaces as uncertainty, not as fact.
"""

from __future__ import annotations

from app.orchestration.escalation import (
    ImpactInputs,
    decide_escalation,
    human_review_summary,
)
from tests.fixtures.cases import route_case


def _adjudicate(client, case_id, rid, key=None):
    headers = {"X-Reviewer-Id": rid}
    if key:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/v1/disputes/{case_id}/adjudicate", headers=headers).json()


def test_missing_distance_telemetry_is_not_a_confident_ruling(client, reader, store, rid):
    # planned/actual absent → deviation cannot be measured → low confidence → escalate.
    case = route_case(reader, store=store, case_id="DSP-000045", ride_id="RIDE-1",
                      planned_km=10.0, actual_km=14.0, quoted_cents=1000, charged_cents=1400)
    reader.routes["RIDE-1"].__dict__  # touch
    # Blank out the distances so deviation_pct is unmeasurable.
    from app.persistence.reader import RouteRecord
    reader.routes["RIDE-1"] = RouteRecord(
        ride_id="RIDE-1", planned_distance_km=0.0, actual_distance_km=0.0,
        planned_duration_s=1500, actual_duration_s=1700,
    )
    body = _adjudicate(client, "DSP-000045", rid)
    assert body["judge"]["confidence"] < 0.70
    assert body["status"] == "escalated"


def test_high_impact_escalates_with_summary(client, reader, store, rid):
    # Charged - quoted excess >= $25.00 (2500c) → high impact → escalate with summary.
    route_case(reader, store=store, case_id="DSP-000046", ride_id="RIDE-2",
               planned_km=10.0, actual_km=40.0, quoted_cents=3000, charged_cents=9000)
    body = _adjudicate(client, "DSP-000046", rid)
    assert body["status"] == "escalated"
    assert "high_impact" in body["judge"]["escalation"]["reasons"]
    summary = body["judge"]["escalation"]["human_review_summary"]
    for header in ("QUESTION TO DECIDE", "EVIDENCE RELIED ON", "WHY ESCALATED",
                   "RIDER ARGUED", "DRIVER ARGUED"):
        assert header in summary


def test_safety_signal_always_escalates_even_when_confident(client, reader, store, rid):
    # A confident route case, but a safety flag in chat → escalate regardless (RP-SAFETY).
    case = route_case(reader, store=store, case_id="DSP-000047", ride_id="RIDE-3",
                      planned_km=10.0, actual_km=10.5, quoted_cents=1000, charged_cents=1050)
    from app.persistence.reader import ChatLog, ChatMessage
    reader.chats["RIDE-3"] = ChatLog(
        ride_id="RIDE-3",
        messages=[ChatMessage(seq=1, role="rider", at="t", text="threat", kind="safety_flag")],
    )
    body = _adjudicate(client, "DSP-000047", rid)
    assert body["status"] == "escalated"
    assert "safety_incident" in body["judge"]["escalation"]["reasons"]


def test_malformed_evidence_surfaces_as_uncertainty(client, reader, store, rid):
    case = route_case(reader, store=store, case_id="DSP-000048", ride_id="RIDE-4",
                      planned_km=10.0, actual_km=13.0, quoted_cents=1000, charged_cents=1300,
                      justified=True)
    # Append a structurally malformed evidence ref (bad class/verification enums).
    from app.persistence.reader import EvidenceRef
    case.evidence.append(
        EvidenceRef(evidence_id="EV-BAD", class_="not_a_real_class", source="system_record",
                    verification_status="not_a_status", payload={"x": 1})
    )
    body = _adjudicate(client, "DSP-000048", rid)
    # Malformed record → insufficiency → escalation, not a confident fact-based ruling.
    assert body["status"] == "escalated"


def test_escalation_unit_safety_regardless_of_confidence():
    d = decide_escalation(
        ruling_type="no_action", confidence=0.99, recommended_amount_cents=0,
        disputed_fare_component_cents=1000,
        impact=ImpactInputs(category="route_deviation", amount_cents=0, fraud_risk=0.0,
                            party_disputes_30d=0, safety_signal=True),
        confidence_threshold=0.70, high_impact_amount_cents=2500, goodwill_cap_cents=1500,
        fraud_threshold=0.60, insufficient=False,
    )
    assert d.escalated is True
    assert "safety_incident" in d.reasons


def test_human_review_summary_is_complete():
    s = human_review_summary(
        category="no_show", question="Was the fee valid?",
        evidence_relied_on=["EV-1"], conflict_or_gap="gap", rider_argument="r",
        driver_argument="d", reasons=["confidence_below_threshold"],
    )
    assert "QUESTION TO DECIDE: Was the fee valid?" in s
    assert "EVIDENCE RELIED ON: EV-1" in s
