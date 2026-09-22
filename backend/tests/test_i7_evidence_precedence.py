"""I-7 — unverified evidence cannot outrank a verified record.

An appeal where unverified chat text contradicts verified GPS must NOT flip the ruling — it
must hold or escalate.
"""

from __future__ import annotations

from app.evidence.models import Evidence, Verification
from app.evidence.precedence import EvidencePrecedence, FactualQuestion
from app.domain import EvidenceClass, EvidenceSource, VerificationStatus, Visibility
from tests.fixtures.cases import noshow_case


def _ev(evidence_id, status, payload, source):
    return Evidence(
        evidence_id=evidence_id, case_id="DSP-1",
        class_=EvidenceClass.gps_telemetry if status == "verified" else EvidenceClass.chat_log,
        source=EvidenceSource(source),
        verification=Verification(status=VerificationStatus(status), method="m"),
        visibility=Visibility.both, payload=payload,
    )


def test_precedence_verified_controls_and_flags_conflict():
    verified = _ev("EV-GPS", "verified", {"min_distance_to_pickup_m": 20.0}, "system_record")
    unverified = _ev("EV-CHAT", "unverified", {"text": "driver never came"}, "rider_submitted")
    ep = EvidencePrecedence()
    q = FactualQuestion(key="arrival", speaking_evidence=(verified, unverified))
    out = ep.resolve(q, contradicts={"EV-CHAT"})
    assert out.verified_present is True
    assert verified in out.controlling
    assert unverified in out.outranked
    assert out.conflict is True  # raises uncertainty; must not flip


def test_appeal_with_unverified_contradiction_does_not_flip(client, reader, store, rid):
    # Base case: driver DID arrive (verified GPS 20m), waited, contacted → fee valid → no_action.
    case = noshow_case(reader, store=store, case_id="DSP-000045", ride_id="RIDE-1",
                       reached_pickup=True, waited_seconds=330, contact_attempt=True,
                       fee_cents=400, min_dist_m=20.0)
    base = client.post("/api/v1/disputes/DSP-000045/adjudicate",
                       headers={"X-Reviewer-Id": rid}).json()
    assert base["judge"]["ruling_type"] == "no_action"

    # Appeal: append UNVERIFIED chat claiming the driver never arrived, contradicting the
    # verified GPS on the SAME factual question.
    case.evidence.append(
        type(case.evidence[0])(
            evidence_id="EV-APPEAL-U", class_="chat_log", source="rider_submitted",
            visibility="both", verification_status="unverified",
            recorded_at="2026-09-22T08:00:00Z", provenance={},
            payload={"text": "the driver was never here", "_question": "arrival",
                     "_contradicts_verified": True},
        )
    )
    # Re-adjudicate the appeal (new idempotency scope).
    appeal = client.post("/api/v1/disputes/DSP-000045/adjudicate",
                         headers={"X-Reviewer-Id": rid, "Idempotency-Key": "appeal-1"}).json()
    # The unverified contradiction may NOT flip no_action -> refund. It holds or escalates.
    assert appeal["judge"]["ruling_type"] != "refund"
    assert appeal["status"] in ("resolved", "escalated")
    # And the verified record is what the reasoning rests on.
    assert "verified" in appeal["judge"]["reasoning"].lower()
