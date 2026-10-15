from pathlib import Path

from app.domain import EvidenceClass, EvidenceSource, VerificationStatus, Visibility
from app.evidence.models import Evidence, Verification
from app.orchestration.official_gate import review_gaps, validate_final_output
from app.orchestration.rules_first import clear_ruling, rule_advocate, verify_rule_advocates
from app.api.container import Container
from app.evidence.external import DisabledExternalSource
from app.orchestration.orchestrator import Orchestrator
from app.policy.loader import load_policy
from app.policy import evaluator
from app.providers.base import ProviderMeta
from app.providers.deterministic_mock import DeterministicMockProvider
from app.persistence.store import ResultStore
from app.settings import Settings
from tests.fixtures.cases import route_case
from tests.fixtures.reader import FixtureReader


POLICY = load_policy("ryde-policy-1.0.0", explicit_path=str(
    Path(__file__).resolve().parents[2] / "database/seed/policy/ryde-policy-1.0.0.json"
))
POLICY_NEXT = load_policy("ryde-policy-1.1.0", explicit_path=str(
    Path(__file__).resolve().parents[2] / "database/seed/policy/ryde-policy-1.1.0.json"
))


def context(category, facts):
    return evaluator.evaluate(category, facts, POLICY)


def evidence(eid, payload):
    return Evidence(
        evidence_id=eid, case_id="DSP-100001", class_=EvidenceClass.fare,
        source=EvidenceSource.system_record,
        verification=Verification(status=VerificationStatus.verified, method="test"),
        visibility=Visibility.both, payload=payload,
    )


def test_clear_route_case_uses_rules_without_model_proposal():
    rows = [evidence("EV-000001", {"quoted_fare_cents": 1200}),
            evidence("EV-000002", {"charged_fare_cents": 1200}),
            evidence("EV-000003", {"actual_distance_km": 7.0})]
    facts = {
        "ride": {"verification_status": "verified", "quoted_fare_cents": 1200,
                 "charged_fare_cents": 1200},
        "route": {"verification_status": "verified", "actual_distance_km": 7.0},
        "fare": {},
    }
    ruling = clear_ruling("route_deviation", facts, rows, "2026-10-15T00:00:00Z", context("route_deviation", facts))
    assert ruling is not None
    assert ruling["ruling_type"] == "no_action"
    assert ruling["provider"]["kind"] == "rules-engine"
    assert ruling["_synthetic"] is False


def test_clear_no_show_waiver_uses_published_voucher_amount():
    filed_at = "2026-10-15T00:03:00Z"
    facts = {
        "ride": {"verification_status": "verified", "service_tier": "RydeX",
                 "accepted_at": "2026-10-15T00:00:00Z",
                 "cancellation_timestamp": "2026-10-15T00:02:00Z",
                 "cancellation_actor": "rider"},
        "route": {}, "fare": {"cancellation_fee_cents": 661}, "app_events": [],
    }
    rows = [evidence("EV-000011", {"cancellation_fee_cents": 661}),
            evidence("EV-000012", {"cancellation_timestamp": "2026-10-15T00:02:00Z"})]
    policy_context = context("no_show_charge", facts)
    ruling = clear_ruling("no_show_charge", facts, rows, filed_at, policy_context)
    assert ruling is not None
    assert ruling["ruling_type"] == "refund"
    assert ruling["recommended_action"]["delivery"] == "voucher"
    assert ruling["recommended_action"]["amount"] == {"amount_cents": 661, "currency": "SGD"}
    assert not review_gaps("no_show_charge", facts, filed_at, ruling, [], [])


def test_clear_fare_case_requires_exact_verified_itemised_reconciliation():
    facts = {"ride": {"verification_status": "verified", "charged_fare_cents": 1200},
             "fare": {"verification_status": "verified", "total_fare_cents": 1200,
                      "components": [{"name": "trip fare", "amount_cents": 1000},
                                     {"name": "platform fee", "amount_cents": 200}]},
             "route": {}}
    rows = [evidence("EV-000021", {"charged_fare_cents": 1200, "total_fare_cents": 1200,
                                    "components": facts["fare"]["components"]})]
    ctx = evaluator.evaluate("fare_calculation", facts, POLICY_NEXT)
    ruling = clear_ruling("fare_calculation", facts, rows, "2026-10-15T00:00:00Z", ctx)
    assert ruling is not None and ruling["ruling_type"] == "no_action"
    facts["fare"]["components"][1]["amount_cents"] = 250
    assert clear_ruling("fare_calculation", facts, rows, "2026-10-15T00:00:00Z", ctx) is None


def test_other_cancellation_fee_uses_rider_waiver_only_when_fee_type_is_explicit():
    filed_at = "2026-10-15T00:03:00Z"
    facts = {"ride": {"verification_status": "verified", "service_tier": "RydeX",
                       "accepted_at": "2026-10-15T00:00:00Z",
                       "cancellation_timestamp": "2026-10-15T00:02:00Z",
                       "cancellation_actor": "rider"},
             "route": {}, "fare": {"cancellation_fee_cents": 661},
             "app_events": [], "filing": {"category_details": {"fee_type": "rider_cancellation"}}}
    rows = [evidence("EV-000022", {"cancellation_fee_cents": 661}),
            evidence("EV-000023", {"cancellation_timestamp": "2026-10-15T00:02:00Z"})]
    ctx = evaluator.evaluate("other_cancellation_fee", facts, POLICY_NEXT)
    ruling = clear_ruling("other_cancellation_fee", facts, rows, filed_at, ctx)
    assert ruling is not None and ruling["ruling_type"] == "refund"
    assert ruling["recommended_action"]["amount"] == {"amount_cents": 661, "currency": "SGD"}
    facts["filing"]["category_details"]["fee_type"] = "driver_payout"
    assert clear_ruling("other_cancellation_fee", facts, rows, filed_at, ctx) is None


def test_clear_waiting_fee_waiver_is_a_five_dollar_voucher_and_not_driver_payout():
    filed_at = "2026-10-15T01:00:00Z"
    facts = {"ride": {"verification_status": "verified", "service_tier": "RydeX",
                       "status": "completed", "completed_at": "2026-10-15T00:20:00Z"},
             "fare": {"verification_status": "verified", "waiting_fare_cents": 500},
             "route": {"verification_status": "verified", "driver_wait_seconds": 180,
                       "driver_arrival_at": "2026-10-15T00:17:00Z"},
             "app_events": [], "filing": {"category_details": {"fee_type": "rider_waiting"}}}
    rows = [evidence("EV-000024", {"waiting_fare_cents": 500}),
            evidence("EV-000025", {"driver_waited_seconds": 180}),
            evidence("EV-000026", {"completed_at": "2026-10-15T00:20:00Z"})]
    ctx = evaluator.evaluate("other_cancellation_fee", facts, POLICY_NEXT)
    assert "RY-WAIVER-002" in ctx.rule_ids()
    ruling = clear_ruling("other_cancellation_fee", facts, rows, filed_at, ctx)
    assert ruling is not None
    assert ruling["recommended_action"]["amount"] == {"amount_cents": 500, "currency": "SGD"}
    assert ruling["recommended_action"]["delivery"] == "voucher"
    assert not review_gaps("other_cancellation_fee", facts, filed_at, ruling, [], [])
    facts["filing"]["category_details"]["fee_type"] = "driver_payout"
    assert clear_ruling("other_cancellation_fee", facts, rows, filed_at, ctx) is None


def test_uncertain_route_case_is_left_for_repair_and_model_review():
    rows = [evidence("EV-000001", {"quoted_fare_cents": 1200}),
            evidence("EV-000002", {"charged_fare_cents": 1400})]
    facts = {"ride": {"verification_status": "verified", "quoted_fare_cents": 1200,
                       "charged_fare_cents": 1400}, "route": {"verification_status": "verified"}}
    assert clear_ruling("route_deviation", facts, rows, "2026-10-15T00:00:00Z", context("route_deviation", facts)) is None


def test_advocate_repairs_are_checked_against_visible_evidence():
    rows = [evidence("EV-000001", {"charged_fare_cents": 1200})]
    rider = rule_advocate("rider", rows, context("route_deviation", {}).rule_ids(),
                          ["Confirm the recorded fare"])
    driver = rule_advocate("driver", rows, context("route_deviation", {}).rule_ids())
    assert rider["claims"][0]["citations"][0]["valid"] is True
    assert verify_rule_advocates(rider, driver, rows) == []


def test_independent_validator_rejects_unverified_decisive_evidence():
    row = evidence("EV-000001", {"charged_fare_cents": 1200}).model_copy(update={
        "verification": Verification(status=VerificationStatus.unverified, method="test")
    })
    facts = {"ride": {"verification_status": "verified", "quoted_fare_cents": 1200,
                       "charged_fare_cents": 1200}, "route": {"verification_status": "verified"},
             "fare": {}}
    judge = {"ruling_type": "no_action", "recommended_action": {"delivery": "none"},
             "policy_references": context("route_deviation", facts).rule_ids(), "evidence_references": ["EV-000001"],
             "decisive_facts": [{"fact": "The fare matched.", "evidence_references": ["EV-000001"]}]}
    gaps = validate_final_output("route_deviation", facts, "2026-10-15T00:00:00Z",
                                 judge, [], [], [row], context("route_deviation", facts))
    assert any("unverified evidence" in gap for gap in gaps)


def test_independent_validator_checks_judge_field_values():
    row = evidence("EV-000001", {"charged_fare_cents": 1200})
    facts = {"ride": {"verification_status": "verified", "quoted_fare_cents": 1200,
                       "charged_fare_cents": 1200}, "route": {"verification_status": "verified"},
             "fare": {}}
    judge = {"provider": {"kind": "llm"}, "ruling_type": "no_action",
             "recommended_action": {"delivery": "none"},
             "policy_references": context("route_deviation", facts).rule_ids(),
             "evidence_references": ["EV-000001"],
             "decisive_facts": [{"fact": "The fare matched.",
                 "evidence_references": ["EV-000001"],
                 "citations": [{"evidence_id": "EV-000001", "field_path": "charged_fare_cents",
                                "observed_value": 9999}]}]}
    gaps = validate_final_output("route_deviation", facts, "2026-10-15T00:00:00Z",
                                 judge, [], [], [row], context("route_deviation", facts))
    assert any("invalid Judge evidence citation" in gap for gap in gaps)


def test_clear_case_does_not_call_configured_live_provider():
    class NoCallProvider:
        meta = ProviderMeta(kind="llm", model="gemini-test", display_name="Gemini test")

        def complete(self, prompt, response_schema):
            raise AssertionError("clear ruling must not call Gemini")

    reader = FixtureReader()
    store = ResultStore()
    case = route_case(reader, store=store, case_id="DSP-000990", ride_id="RIDE-000990",
                      planned_km=10.0, actual_km=11.0, quoted_cents=1200, charged_cents=1200)
    reader.rides[case.ride_id] = reader.rides[case.ride_id].model_copy(update={
        "service_tier": "RydeX", "verification_status": "verified"
    })
    reader.routes[case.ride_id] = reader.routes[case.ride_id].model_copy(update={
        "verification_status": "verified"
    })
    settings = Settings(_env_file=None, model_provider="openai_compatible",
                        policy_version="ryde-policy-1.0.0", currency="SGD")
    orchestrator = Orchestrator(reader=reader, provider=NoCallProvider(), policy=POLICY,
                                external=DisabledExternalSource(), store=store, settings=settings)
    result = orchestrator.run_case(case)
    assert result["judge"]["provider"]["kind"] == "rules-engine"
    assert result["judge"]["ruling_type"] == "no_action"
    assert result["model_proposed_ruling"] is None
    assert not any(event["event"] == "gemini_escalation" for event in result["trace"])


def test_unresolvable_route_gap_stops_after_one_check_and_routes_to_human():
    reader = FixtureReader()
    store = ResultStore()
    case = route_case(reader, store=store, case_id="DSP-000991", ride_id="RIDE-000991",
                      planned_km=10.0, actual_km=16.0, quoted_cents=1200, charged_cents=1600)
    settings = Settings(_env_file=None, model_provider="deterministic_mock",
                        policy_version="ryde-policy-1.0.0", currency="SGD")
    orchestrator = Orchestrator(reader=reader, provider=DeterministicMockProvider(), policy=POLICY,
                                external=DisabledExternalSource(), store=store, settings=settings)
    result = orchestrator.run_case(case)
    events = [item["event"] for item in result["trace"]]
    assert events.count("review_round") == 1
    assert events.count("advocate_repair_requested") == 1
    assert events.count("evidence_gap_check") >= 1
    assert "human_review_without_model" in events
    assert "model_escalation" not in events
    assert result["status"] == "escalated"
    assert result["model_proposed_ruling"] is None


def test_interpretive_uncertainty_still_uses_configured_judge(monkeypatch):
    import app.orchestration.orchestrator as orchestration

    monkeypatch.setattr(orchestration, "model_review_blockers", lambda *args, **kwargs: [])
    reader = FixtureReader()
    store = ResultStore()
    case = route_case(reader, store=store, case_id="DSP-000993", ride_id="RIDE-000993",
                      planned_km=10.0, actual_km=16.0, quoted_cents=1200, charged_cents=1600)
    settings = Settings(_env_file=None, model_provider="deterministic_mock",
                        policy_version="ryde-policy-1.0.0", currency="SGD")
    orchestrator = Orchestrator(reader=reader, provider=DeterministicMockProvider(), policy=POLICY,
                                external=DisabledExternalSource(), store=store, settings=settings)
    result = orchestrator.run_case(case)
    events = [item["event"] for item in result["trace"]]
    assert events.count("review_round") == 1
    assert "model_escalation" in events
    assert "human_review_without_model" not in events


def test_repaired_case_stops_early_without_provider_call(monkeypatch):
    import app.orchestration.rules_first as rules

    original = rules.verify_rule_advocates
    calls = {"count": 0}

    def transient_finding(rider, driver, evidence_rows):
        calls["count"] += 1
        if calls["count"] == 1:
            return [{"party": "rider", "reason": "initial citation requires correction"}]
        return original(rider, driver, evidence_rows)

    monkeypatch.setattr(rules, "verify_rule_advocates", transient_finding)

    class NoCallProvider:
        meta = ProviderMeta(kind="llm", model="gemini-test", display_name="Gemini test")

        def complete(self, prompt, response_schema):
            raise AssertionError("repaired clear case must stop before Gemini")

    reader = FixtureReader()
    store = ResultStore()
    case = route_case(reader, store=store, case_id="DSP-000992", ride_id="RIDE-000992",
                      planned_km=10.0, actual_km=11.0, quoted_cents=1200, charged_cents=1200)
    reader.rides[case.ride_id] = reader.rides[case.ride_id].model_copy(update={
        "service_tier": "RydeX", "verification_status": "verified"
    })
    reader.routes[case.ride_id] = reader.routes[case.ride_id].model_copy(update={
        "verification_status": "verified"
    })
    settings = Settings(_env_file=None, model_provider="openai_compatible",
                        policy_version="ryde-policy-1.0.0", currency="SGD")
    orchestrator = Orchestrator(reader=reader, provider=NoCallProvider(), policy=POLICY,
                                external=DisabledExternalSource(), store=store, settings=settings)

    result = orchestrator.run_case(case)
    events = [item["event"] for item in result["trace"]]
    assert events.count("review_round") == 1
    assert "repair_satisfied" in events
    assert "gemini_escalation" not in events
    assert result["judge"]["provider"]["kind"] == "rules-engine"
