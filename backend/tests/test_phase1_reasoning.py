from __future__ import annotations

from datetime import datetime, timezone

from app.orchestration.escalation import ImpactInputs, decide_escalation, human_review_summary
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.orchestrator import _recency_weight
from app.models.fraud_detector import FraudDetector
from app.models.evidence_auditor import EvidenceAuditor
from app.evidence.models import Evidence, Verification
from tests.fixtures.cases import route_case
from app.providers.deterministic_mock import DeterministicMockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.settings import Settings
from pydantic import ValidationError


def test_deterministic_evidence_auditor_flags_wrong_fabricated_unsupported_and_conflicting_claims():
    provider = DeterministicMockProvider()
    actual_evidence = [
        {"evidence_id": "EV-A", "payload": {"fare_cents": 1200}},
        {"evidence_id": "EV-B", "payload": {"fare_cents": 1400}},
    ]
    claims = {
        "rider": {"claims": [
            {"text": "Fare was 1200.", "citations": [
                {"evidence_id": "EV-A", "field_path": "fare_cents", "observed_value": 1200}
            ]},
            {"text": "The driver waited 8 minutes.", "citations": [
                {"evidence_id": "MISSING-EV", "field_path": "waited_seconds", "observed_value": 480}
            ]},
            {"text": "A further uncited claim.", "citations": []},
        ]},
        "driver": {"claims": [
            {"text": "Fare was 1400.", "citations": [
                {"evidence_id": "EV-B", "field_path": "fare_cents", "observed_value": 1400}
            ]},
            {"text": "The fare was 900.", "citations": [
                {"evidence_id": "EV-A", "field_path": "fare_cents", "observed_value": 900}
            ]},
        ]},
    }
    completion = provider.complete(
        {"role": "evidence_auditor", "advocates": claims, "evidence": actual_evidence}, {}
    )
    kinds = {finding["classification"] for finding in completion.data["findings"]}
    assert {"incorrect", "fabrication_suspected", "unsupported", "contradicted"} <= kinds
    assert all(finding["materiality"] == "unknown" for finding in completion.data["findings"])


def test_evidence_and_fraud_assessment_match_case_result_contract_shapes():
    evidence = Evidence(
        evidence_id="EV-000001", case_id="DSP-000001", class_="fare",
        source="system_record", verification=Verification(status="verified"),
        payload={"fare_cents": 1200},
    )
    claims = {
        "rider": {"claims": [{
            "text": "Fare was 900.",
            "citations": [{
                "evidence_id": "EV-000001", "field_path": "fare_cents",
                "observed_value": 900, "valid": False,
            }],
        }]},
        "driver": {"claims": []},
    }
    auditor = EvidenceAuditor(DeterministicMockProvider())
    audit = auditor.audit(
        rider=claims["rider"], driver=claims["driver"], evidence=[evidence],
        category="route_deviation", policy_rules=[],
    )
    assert set(audit) == {"findings", "provider"}
    assert set(audit["findings"][0]) == {
        "party", "claim_text", "classification", "confidence", "explanation",
        "evidence_references", "materiality",
    }
    fraud = FraudDetector(DeterministicMockProvider()).assess(
        party="rider", profile=None, evidence=[evidence], evidence_audit=audit["findings"],
        advocate_claims=claims,
    )
    assert set(fraud) == {"risk_score", "confidence", "findings", "provider"}
    assert set(fraud["findings"][0]) == {
        "finding_type", "party", "summary", "source_fields", "evidence_ids"
    }


def test_safety_auto_ruling_gate_requires_verified_decisive_facts_and_no_material_flags(
    container,
):
    orchestrator = container.orchestrator()
    verified = Evidence(
        evidence_id="EV-SAFE-1", case_id="DSP-000901", class_="chat_log",
        source="system_record", verification=Verification(status="verified"),
        payload={"text": "platform-recorded incident"},
    )
    unverified = Evidence(
        evidence_id="EV-SAFE-2", case_id="DSP-000901", class_="chat_log",
        source="rider_submitted", verification=Verification(status="unverified"),
        payload={"text": "party statement"},
    )
    ruling = {
        "confidence": 0.91,
        "decisive_facts": [{"fact": "Platform log records the incident.",
                            "evidence_references": [verified.evidence_id]}],
    }
    allowed = dict(
        judge_out=ruling, evidence=[verified], audit_findings=[], precedence_notes=[],
        contradiction_note=None, insufficient=False, confidence_threshold=0.70,
    )
    assert orchestrator._safety_auto_ruling_eligible(**allowed) is True

    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "evidence": [unverified]}
    ) is False
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "judge_out": {**ruling, "decisive_facts": []}}
    ) is False
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "judge_out": {**ruling, "decisive_facts": [
            {"fact": "unknown reference", "evidence_references": ["EV-MISSING"]}
        ]}}
    ) is False
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "judge_out": {**ruling, "confidence": 0.69}}
    ) is False
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "audit_findings": [{
            "classification": "fabrication_suspected", "materiality": "material",
        }]}
    ) is False
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "audit_findings": [{
            "classification": "contradicted", "materiality": "unknown",
        }]}
    ) is False
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "audit_findings": [{"classification": "contradicted"}]}
    ) is False
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "audit_findings": [{
            "classification": "incorrect", "materiality": "non_material",
        }]}
    ) is True
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "precedence_notes": ["incident details"]}
    ) is False
    assert orchestrator._safety_auto_ruling_eligible(
        **{**allowed, "insufficient": True}
    ) is False


def test_deterministic_safety_judge_emits_explicit_missing_fact_contract():
    output = DeterministicMockProvider().complete(
        {
            "role": "judge", "category": "safety_incident", "measurements": {},
            "policy_rules": [], "evidence_ids": ["EV-001"],
        }, {},
    ).data
    assert output["decisive_facts"] == [{
        "fact": "The deterministic provider cannot identify decisive safety facts.",
        "evidence_references": [],
    }]


def test_escalation_decision_does_not_accept_a_fraud_risk_trigger():
    result = decide_escalation(
        ruling_type="no_action",
        confidence=0.95,
        recommended_amount_cents=0,
        disputed_fare_component_cents=1000,
        impact=ImpactInputs(
            category="route_deviation",
            amount_cents=0,
            party_disputes_30d=0,
            safety_signal=False,
        ),
        confidence_threshold=0.70,
        high_impact_amount_cents=2500,
        goodwill_cap_cents=1500,
        insufficient=False,
    )
    assert result.escalated is False
    assert result.reasons == []


def test_deterministic_judge_uses_fraud_only_to_weight_unsupported_claims():
    provider = DeterministicMockProvider()
    prompt = {
        "role": "judge",
        "category": "route_deviation",
        "measurements": {"deviation_pct": 10, "quoted_fare_cents": 1000,
                         "charged_fare_cents": 1000},
        "thresholds": {"deviation_tolerance_pct": 15},
        "evidence_ids": [],
        "policy_rules": [],
        "precedence_notes": [],
        "currency": "SGD",
    }
    ordinary = provider.complete({
        **prompt, "fraud_assessment": {"risk_score": 0.0, "influence_weight": 2.0}
    }, {})
    unsupported = provider.complete({
        **prompt,
        "fraud_assessment": {"risk_score": 1.0, "influence_weight": 2.0},
        "evidence_audit": [{"classification": "unsupported"}],
    }, {})
    assert ordinary.data["confidence"] == 0.88
    assert unsupported.data["confidence"] < ordinary.data["confidence"]
    assert unsupported.data["ruling_type"] == ordinary.data["ruling_type"]


def test_fraud_detector_returns_case_specific_structured_assessment():
    detector = FraudDetector(DeterministicMockProvider())
    assessment = detector.assess(
        party="rider",
        profile={"disputes_last_30d": 2, "disputes_total": 5},
        evidence=[],
        evidence_audit=[{
            "classification": "fabrication_suspected", "party": "rider",
            "claim_text": "Claim.", "explanation": "Cited ID absent from bundle.",
            "confidence": 0.9, "evidence_references": [],
        }],
        advocate_claims={"rider": {"claims": []}, "driver": {"claims": []}},
    )
    assert assessment["risk_score"] == 0.8
    assert assessment["confidence"] == 0.75
    assert "profile_history.disputes_last_30d" in assessment["findings"][0]["source_fields"]
    assert "fabrication_suspected" in assessment["findings"][1]["summary"]


def test_profile_fraud_signal_reaches_judge_without_escalating_by_itself(
    client, reader, store, rid
):
    case = route_case(
        reader, store=store, case_id="DSP-009901", ride_id="RIDE-009901",
        planned_km=10.0, actual_km=14.0, quoted_cents=1000, charged_cents=1400,
        rider_disputes_30d=2,
    )
    response = client.post(
        f"/api/v1/disputes/{case.case_id}/adjudicate", headers={"X-Reviewer-Id": rid}
    )
    result = response.json()
    assert result["judge"]["provider"]["display_name"] == "local deterministic"
    assert set(result["evidence_audit"]) == {"findings", "provider"}
    assert result["evidence_audit"]["provider"]["display_name"] == "local deterministic"
    assert set(result["fraud_assessment"]) == {
        "risk_score", "confidence", "findings", "provider", "influence_weight", "assessment_note"
    }
    assert result["fraud_assessment"]["influence_weight"] == 3.0
    assert "never escalate solely" in result["fraud_assessment"]["assessment_note"]
    assert 0 <= result["fraud_assessment"]["risk_score"] <= 1
    assert result["fraud_assessment"]["provider"]["display_name"] == "local deterministic"
    assert "Fraud-risk assessment" in result["judge"]["reasoning"]
    assert result["status"] == "resolved"


def test_human_review_summary_says_what_records_show_and_do_not_show():
    summary = human_review_summary(
        category="route_deviation",
        question="Was the fare overcharged?",
        evidence_relied_on=["EV-1"],
        conflict_or_gap="missing distance telemetry",
        rider_argument="overcharged",
        driver_argument="valid fare",
        reasons=["insufficient_or_contradictory_evidence"],
        evidence_shows=["EV-1 (quoted_fare_cents=1200)"],
        evidence_does_not_show=["No verified evidence establishes actual_distance_km."],
        audit_findings=[{
            "classification": "unsupported", "party": "rider",
            "claim_text": "No citation", "confidence": 1.0,
            "explanation": "No citation.", "evidence_references": [],
        }],
        fraud_assessment={"risk_score": 0.4, "findings": [{
            "summary": "Profile history signal.", "evidence_ids": []
        }]},
    )
    assert "EVIDENCE SHOWS: EV-1 (quoted_fare_cents=1200)" in summary
    assert "EVIDENCE DOES NOT SHOW: No verified evidence establishes actual_distance_km." in summary
    assert "EVIDENCE AUDIT: unsupported (rider claim: No citation): No citation." in summary
    assert "FRAUD RISK SIGNALS: risk=0.4" in summary


def test_precedent_recency_uses_configured_half_life():
    reference = datetime(2026, 9, 25, tzinfo=timezone.utc)
    at_half_life = "2025-09-25T00:00:00+00:00"
    assert _recency_weight(reference, at_half_life, 365.0) == 0.5


def _deterministic_route_judgment(*, charged, quoted, precedents, deviation=25):
    return DeterministicMockProvider().complete({
        "role": "judge",
        "category": "route_deviation",
        "measurements": {
            "deviation_pct": deviation,
            "deviation_justified": False,
            "charged_fare_cents": charged,
            "quoted_fare_cents": quoted,
        },
        "thresholds": {"deviation_tolerance_pct": 15, "goodwill_cap_cents": 1500},
        "policy_rules": [
            {"rule_id": "RP-ROUTE-003", "text": "Unjustified deviation requires remedy."},
            {"rule_id": "RP-FARE-001", "text": "Refund only actual excess."},
            {"rule_id": "RP-FARE-004", "text": "Discretionary goodwill up to cap."},
        ],
        "precedents": precedents,
        "judging_weights": {
            "policy_priority": 100,
            "human_approved_weight": 2,
            "model_proposed_weight": 1,
        },
    }, {}).data


def _comp_precedent(case_id, origin, amount, *, effective_weight, recency):
    return {
        "archive_case_id": case_id,
        "ruling_type": "compensation",
        "decision_origin": origin,
        "recommended_action": {"amount": {"amount_cents": amount}},
        "effective_precedent_weight": effective_weight,
        "recency_weight": recency,
    }


def test_deterministic_judge_keeps_clear_policy_refund_over_conflicting_precedent():
    result = _deterministic_route_judgment(
        charged=1800, quoted=1200,
        precedents=[_comp_precedent(
            "ARCHIVE-HUMAN", "human", 500, effective_weight=200, recency=1,
        )],
    )
    assert result["ruling_type"] == "refund"
    assert result["recommended_action"]["amount"]["amount_cents"] == 600
    assert "precedent" not in result["reasoning"].lower()


def test_deterministic_judge_uses_newer_reviewer_approved_precedent_for_open_goodwill():
    # Policy establishes a real, unjustified service failure but no fare excess. RP-FARE-004
    # leaves a capped discretionary decision open; higher human credibility and recency decide.
    older_human = _comp_precedent(
        "ARCHIVE-OLD-HUMAN", "human", 400, effective_weight=1.0, recency=0.25,
    )
    newer_model = _comp_precedent(
        "ARCHIVE-NEW-MODEL", "agent", 900, effective_weight=1.5, recency=1.0,
    )
    newest_human = _comp_precedent(
        "ARCHIVE-NEW-HUMAN", "human", 700, effective_weight=2.0, recency=1.0,
    )
    recent_model_wins_on_recency = _deterministic_route_judgment(
        charged=1200, quoted=1200, precedents=[older_human, newer_model],
    )
    assert recent_model_wins_on_recency["recommended_action"]["amount"]["amount_cents"] == 900

    result = _deterministic_route_judgment(
        charged=1200, quoted=1200,
        precedents=[older_human, newer_model, newest_human],
    )
    assert result["ruling_type"] == "compensation"
    assert result["recommended_action"]["amount"]["amount_cents"] == 700
    assert "reviewer-approved precedent" in result["reasoning"]
    assert "ARCHIVE-NEW-HUMAN" in result["reasoning"]


def test_deterministic_judge_does_not_apply_precedent_when_policy_is_clear_or_evidence_missing():
    precedent = _comp_precedent(
        "ARCHIVE-HUMAN", "human", 500, effective_weight=200, recency=1,
    )
    within_tolerance = _deterministic_route_judgment(
        charged=1200, quoted=1200, deviation=10, precedents=[precedent],
    )
    assert within_tolerance["ruling_type"] == "no_action"
    assert "precedent" not in within_tolerance["reasoning"].lower()

    missing_measurement = _deterministic_route_judgment(
        charged=1200, quoted=1200, deviation=None, precedents=[precedent],
    )
    assert missing_measurement["ruling_type"] == "no_action"
    assert "precedent" not in missing_measurement["reasoning"].lower()


def test_provider_metadata_uses_user_facing_name_without_exposing_it_as_model():
    mock_meta = DeterministicMockProvider().meta.to_api()
    assert mock_meta["display_name"] == "local deterministic"
    assert mock_meta["kind"] == "deterministic-mock"

    gemini = OpenAICompatibleProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-test", api_key="test",
    ).meta.to_api()
    assert gemini["display_name"] == "Gemini"
    assert gemini["model"] == "gemini-test"

    custom = OpenAICompatibleProvider(
        base_url="https://api.example.ai/v1", model="test", api_key="test",
        provider_name="Friendly Provider",
    ).meta.to_api()
    assert custom["display_name"] == "Friendly Provider"


def test_import_settings_use_plain_psycopg_dsn_and_positive_upload_limit():
    settings = Settings(import_database_dsn="postgresql:///ryde_tribunal")
    assert settings.import_max_upload_bytes == 52_428_800
    try:
        Settings(import_max_upload_bytes=0)
    except ValidationError:
        pass
    else:
        raise AssertionError("non-positive import limit should fail settings validation")
    try:
        Settings(import_database_dsn="postgresql+psycopg:///ryde_tribunal")
    except ValidationError:
        pass
    else:
        raise AssertionError("SQLAlchemy URL should fail settings validation")
