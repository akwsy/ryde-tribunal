from pathlib import Path
from app.policy.loader import load_policy
from app.policy.official import factual_values
from app.orchestration.official_gate import review_gaps
from app.orchestration.official_gate import model_review_blockers, explain_gap_source_check
from types import SimpleNamespace
from app.evidence.citation import _values_equal


def facts(wait=180):
    return {"ride":{"service_tier":"RydeX","accepted_at":"2026-10-13T00:00:00Z",
        "cancellation_timestamp":"2026-10-13T00:03:00Z","cancellation_actor":"rider"},
        "fare":{"cancellation_fee_cents":661},"route":{},"app_events":[]}


def test_boundary_measurements_never_contain_outcomes():
    values=factual_values(facts(),"2026-10-13T00:04:00Z")
    assert values["seconds_after_matching"]==180
    assert "ruling_type" not in values


def test_invalid_cash_remedy_and_valid_fee_refund_are_withheld():
    judge={"ruling_type":"refund","recommended_action":{"delivery":"unspecified","amount":{"amount_cents":661,"currency":"SGD"}},
        "decisive_facts":[{"fact":"timing","evidence_references":["EV-000001"]}]}
    assert any("delivery" in gap for gap in review_gaps("no_show_charge",facts(),"2026-10-13T00:04:00Z",judge,[],[]))
    data=facts();data["ride"]["cancellation_timestamp"]="2026-10-13T00:04:00Z"
    judge["recommended_action"]["delivery"]="voucher"
    assert any("invalid cancellation" in gap for gap in review_gaps("no_show_charge",data,"2026-10-13T00:05:00Z",judge,[],[]))


def test_hard_evidence_and_policy_gaps_route_to_human_without_model():
    blockers = model_review_blockers(
        ["Additional fare requires review: no published route refund formula."],
        precedence_notes=["fare"], insufficient=True, decisive_evidence_present=False,
    )
    assert any("Additional fare" in reason for reason in blockers)
    assert any("conflict" in reason.lower() for reason in blockers)
    assert any("missing" in reason.lower() for reason in blockers)


def test_interpretive_question_remains_eligible_for_model_review():
    assert model_review_blockers(
        ["The verified records require interpretation under the applicable rule."],
        decisive_evidence_present=True,
    ) == []


def test_missing_or_conflicting_decisive_gap_skips_model_review():
    blockers = model_review_blockers(
        ["Missing decisive fact: cancellation_actor.",
         "Verified cancellation records disagree about the cancelling party."],
        decisive_evidence_present=True,
    )
    assert len(blockers) == 2


def test_gap_check_names_missing_fact_and_verified_support():
    evidence = [SimpleNamespace(
        evidence_id="EV-000001",
        verification=SimpleNamespace(status=SimpleNamespace(value="verified")),
        payload={"cancellation_actor": "rider"},
    )]
    summary, ids = explain_gap_source_check(
        "Missing decisive fact: cancellation_actor.",
        {"ride": {}, "fare": {}, "filing": {}}, evidence,
    )
    assert "cancellation_actor: verified record present" in summary
    assert ids == ["EV-000001"]


def test_unverified_event_cannot_establish_arrival():
    data=facts();data["app_events"]=[{"event_type":"im_here","verification_status":"unverified"}]
    assert factual_values(data)["arrival_button_recorded"] is False


def test_boolean_citation_is_not_numeric_one():
    assert not _values_equal(True,1)


def test_advanced_grace_only_applies_to_late_matching():
    data=facts();data['ride']['scheduled_at']='2026-10-13T00:17:00Z'
    judge={'ruling_type':'refund','recommended_action':{'delivery':'voucher','amount':{'amount_cents':661,'currency':'SGD'}},'decisive_facts':[{'fact':'timing','evidence_references':['EV-000001']}]}
    assert any('invalid cancellation' in gap for gap in review_gaps('no_show_charge',data,'2026-10-13T00:04:00Z',judge,[],[]))


def test_consistent_material_audit_findings_do_not_force_escalation():
    data={"ride":{"verification_status":"verified","service_tier":"RydeX",
        "quoted_fare_cents":1400,"charged_fare_cents":1400},"fare":{},"route":{}}
    judge={"ruling_type":"no_action","recommended_action":{"delivery":"none"},
        "decisive_facts":[{"fact":"The quoted fare matched the charged fare."}]}
    consistent=[{"classification":"consistent","materiality":"material"}]
    gaps=review_gaps("route_deviation",data,"2026-10-15T00:00:00Z",judge,consistent,[])
    assert not any("audit finding" in gap for gap in gaps)


def test_material_unsupported_audit_finding_still_requires_review():
    data={"ride":{"verification_status":"verified","service_tier":"RydeX",
        "quoted_fare_cents":1400,"charged_fare_cents":1400},"fare":{},"route":{}}
    judge={"ruling_type":"no_action","recommended_action":{"delivery":"none"},
        "decisive_facts":[{"fact":"The quoted fare matched the charged fare."}]}
    unsupported=[{"classification":"unsupported","materiality":"unknown"}]
    gaps=review_gaps("route_deviation",data,"2026-10-15T00:00:00Z",judge,unsupported,[])
    assert any("audit finding" in gap for gap in gaps)


def test_verified_ride_and_fare_ledger_conflict_requires_human_review(reader, store, rid):
    from pathlib import Path
    from app.api.app import create_app
    from app.api.container import build_container
    from app.persistence.reader import FareBreakdown, FareComponent
    from tests.conftest import make_settings
    from tests.fixtures.cases import route_case
    from fastapi.testclient import TestClient

    route_case(reader, case_id="DSP-000061", ride_id="RIDE-000061", planned_km=5,
               actual_km=9, quoted_cents=1400, charged_cents=1625)
    reader.rides["RIDE-000061"] = reader.rides["RIDE-000061"].model_copy(
        update={"verification_status": "verified"}
    )
    reader.fares["RIDE-000061"] = FareBreakdown(
        ride_id="RIDE-000061", total_fare_cents=1400, verification_status="verified",
        components=[FareComponent(name="base", amount_cents=1400)],
    )
    policy_path = Path(__file__).resolve().parents[2] / "database" / "seed" / "policy" / "ryde-policy-1.0.0.json"
    settings = make_settings(policy_version="ryde-policy-1.0.0", policy_path=str(policy_path))
    client = TestClient(create_app(build_container(reader=reader, settings=settings, store=store)))
    headers = {"X-Reviewer-Id": rid}
    filed = client.post("/api/v1/disputes", headers=headers, json={
        "category": "route_deviation", "ride_id": "RIDE-000061", "filed_by": "rider",
        "subject": "Synthetic fare mismatch", "description": "Please check the recorded fare.",
    })
    assert filed.status_code == 201
    result = client.post(f"/api/v1/disputes/{filed.json()['case_id']}/adjudicate", headers=headers)
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "escalated"
    validation = next(event for event in body["trace"]
                      if event["actor"] == "independent_validator" and event["event"] == "final_validation")
    assert "disagree" in validation["summary"]


def test_json_encoded_structured_citation_is_normalized_only_when_exact():
    import json
    from app.models.components import _normalize_structured_citation_value

    stored = [{"name": "ERP toll", "amount_cents": 80}]
    accepted, normalized = _normalize_structured_citation_value(json.dumps(stored), stored)
    assert accepted and normalized == stored
    assert not _normalize_structured_citation_value(json.dumps([{"name": "ERP toll", "amount_cents": 81}]), stored)[0]
    assert not _normalize_structured_citation_value('[{"name":"ERP toll","amount_cents":true}]', stored)[0]
    assert not _normalize_structured_citation_value(str(stored), stored)[0]
    assert _normalize_structured_citation_value("80", 80) == (True, 80)


def test_measurement_validation_accepts_exact_strings_without_coercing_types():
    from app.models.components import _measurement_matches

    assert _measurement_matches("RydeX", "RydeX")
    assert _measurement_matches("2026-10-15T00:00:00Z", "2026-10-15T00:00:00Z")
    assert not _measurement_matches("80", 80)
    assert not _measurement_matches(1, True)


def test_citation_field_catalog_excludes_internal_fields_and_lists_real_paths():
    from app.models.components import _citation_field_catalog

    catalog = _citation_field_catalog([{"evidence_id": "EV-1", "payload": {
        "components": [{"name": "base", "amount_cents": 1400}],
        "_question": "fare", "charged_fare_cents": 1400,
    }}])
    assert catalog == [{"evidence_id": "EV-1", "fields": [
        {"field_path": "payload.components", "observed_value": [{"name": "base", "amount_cents": 1400}]},
        {"field_path": "payload.charged_fare_cents", "observed_value": 1400},
    ]}]


def test_fact_reference_ids_are_derived_from_validated_citations():
    from app.models.components import _normalize_fact_evidence_references

    fact = {"evidence_references": ["EV-UNSUPPORTED"]}
    assert _normalize_fact_evidence_references(fact, {"EV-000002", "EV-000001"})
    assert fact["evidence_references"] == ["EV-000001", "EV-000002"]
    assert not _normalize_fact_evidence_references(fact, set())


def test_duplicate_filing_key_returns_the_same_case_and_rejects_changed_body(client,rid):
    headers={"X-Reviewer-Id":rid,"Idempotency-Key":"submission-file-once"}
    payload={"category":"route_deviation","ride_id":"RIDE-000001","filed_by":"rider","subject":"Test filing","description":"Synthetic test"}
    first=client.post('/api/v1/disputes',headers=headers,json=payload)
    second=client.post('/api/v1/disputes',headers=headers,json=payload)
    assert first.status_code==second.status_code==201
    assert first.json()['case_id']==second.json()['case_id']
    payload['subject']='Different request'
    assert client.post('/api/v1/disputes',headers=headers,json=payload).status_code==409


def test_override_rejects_missing_rationale_before_persisting(client,reader,store,rid):
    from tests.fixtures.cases import route_case
    route_case(reader,store=store,case_id='DSP-000060',ride_id='RIDE-000601',planned_km=10,actual_km=20,quoted_cents=1000,charged_cents=2000)
    client.post('/api/v1/disputes/DSP-000060/adjudicate',headers={'X-Reviewer-Id':rid})
    response=client.post('/api/v1/disputes/DSP-000060/override',headers={'X-Reviewer-Id':rid},json={'ruling_type':'no_action','recommended_action':{'description':'Retain fare'},'reason_code':'other','rationale':''})
    assert response.status_code==422
    assert store.get_case_result('DSP-000060')['reviewer_approved_ruling'] is None
