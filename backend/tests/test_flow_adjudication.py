"""Contract and flow tests (brief §7 — contract and flow, failure and escalation)."""

from __future__ import annotations

from tests.fixtures.cases import add_archive, noshow_case, route_case


def _adjudicate(client, case_id, rid, key=None):
    headers = {"X-Reviewer-Id": rid}
    if key:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/v1/disputes/{case_id}/adjudicate", headers=headers)


def test_route_deviation_end_to_end(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000045", ride_id="RIDE-000123",
               planned_km=13.7, actual_km=18.4, quoted_cents=1370, charged_cents=1840)
    add_archive(reader, "route_deviation")
    r = _adjudicate(client, "DSP-000045", rid)
    assert r.status_code == 200, r.text
    body = r.json()
    # CaseResult is complete — every top-level field present.
    for field in ("case_id", "ride_id", "category", "status", "synthetic",
                  "synthetic_reasoning", "policy_version", "case_facts", "advocates",
                  "judge", "external_findings", "external_unavailable", "urgency",
                  "case_history"):
        assert field in body, f"missing {field}"
    # Both advocates returned case-specific arguments with evidence AND policy refs.
    for side in ("rider", "driver"):
        adv = body["advocates"][side]
        assert adv["argument"]
        assert adv["policy_references"]
        assert any(c["citations"] for c in adv["claims"])
    # Judge returned the full ruling shape.
    j = body["judge"]
    for field in ("ruling_type", "recommended_action", "confidence", "reasoning",
                  "evidence_references", "policy_references", "escalation", "provider"):
        assert field in j
    assert j["ruling_type"] in ("refund", "compensation", "no_action")
    # Unjustified 34% deviation → refund of the excess.
    assert j["ruling_type"] == "refund"
    assert j["measurements"]["deviation_pct"] == 34.3
    assert body["policy_version"] == "ryde-policy-0.1.0"


def test_no_show_end_to_end(client, reader, store, rid):
    noshow_case(reader, store=store, case_id="DSP-000046", ride_id="RIDE-000200",
                reached_pickup=True, waited_seconds=320, contact_attempt=True, fee_cents=400)
    r = _adjudicate(client, "DSP-000046", rid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "no_show"
    # Driver arrived, waited, contacted → fee valid → no_action.
    assert body["judge"]["ruling_type"] == "no_action"


def test_model_work_persisted_and_retrievable(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000047", ride_id="RIDE-000300",
               planned_km=10.0, actual_km=11.0, quoted_cents=1000, charged_cents=1100)
    _adjudicate(client, "DSP-000047", rid)
    # Retrievable via GET after the request completes.
    got = client.get("/api/v1/disputes/DSP-000047")
    assert got.status_code == 200
    assert got.json()["case_id"] == "DSP-000047"
    # Model work persisted through the backend's OWN layer (tribunal.model_work_*), NOT the
    # reader — the read contract has no write surface (§5/§6).
    work = store.get_model_work("DSP-000047")
    assert work and work[0]["case_id"] == "DSP-000047"
    assert not hasattr(reader, "persist_model_work")


def test_policy_version_recorded_and_document_matches(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000048", ride_id="RIDE-000400",
               planned_km=10.0, actual_km=15.0, quoted_cents=1000, charged_cents=1500)
    body = _adjudicate(client, "DSP-000048", rid).json()
    version = body["policy_version"]
    doc = client.get(f"/api/v1/policy/{version}")
    assert doc.status_code == 200
    ids = {r["rule_id"] for r in doc.json()["rules"]}
    assert "RP-ROUTE-003" in ids


def test_approve_appends_history_without_destroying_ruling(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000049", ride_id="RIDE-000500",
               planned_km=10.0, actual_km=10.5, quoted_cents=1000, charged_cents=1050)
    original = _adjudicate(client, "DSP-000049", rid).json()
    orig_ruling = original["judge"]["ruling_type"]
    r = client.post("/api/v1/disputes/DSP-000049/approve",
                    json={"note": "looks right"}, headers={"X-Reviewer-Id": rid})
    assert r.status_code == 200
    body = r.json()
    assert body["judge"]["ruling_type"] == orig_ruling  # original untouched
    assert any(e["event"] == "approved" for e in body["case_history"])


def test_override_appends_and_rejects_bad_reason_code(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000050", ride_id="RIDE-000600",
               planned_km=10.0, actual_km=20.0, quoted_cents=1000, charged_cents=2000)
    original = _adjudicate(client, "DSP-000050", rid).json()
    orig_ruling = original["judge"]["ruling_type"]

    # Bad reason_code rejected.
    bad = client.post("/api/v1/disputes/DSP-000050/override",
                      json={"ruling_type": "no_action", "reason_code": "because_i_said_so",
                            "rationale": "x"},
                      headers={"X-Reviewer-Id": rid})
    assert bad.status_code == 422

    # Valid override appended; original ruling preserved in the judge block.
    ok = client.post("/api/v1/disputes/DSP-000050/override",
                     json={"ruling_type": "no_action", "reason_code": "policy_misapplied",
                           "rationale": "deviation was rider-requested"},
                     headers={"X-Reviewer-Id": rid})
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "overridden"
    assert body["judge"]["ruling_type"] == orig_ruling  # NOT destroyed
    ovr = [e for e in body["case_history"] if e["event"] == "overridden"]
    assert ovr and ovr[0]["payload"]["original_ruling_type"] == orig_ruling


def test_mutating_routes_require_reviewer_id(client, reader, store):
    route_case(reader, store=store, case_id="DSP-000051", ride_id="RIDE-000700",
               planned_km=10.0, actual_km=12.0, quoted_cents=1000, charged_cents=1200)
    # adjudicate
    assert client.post("/api/v1/disputes/DSP-000051/adjudicate").status_code == 401
    # approve / override
    assert client.post("/api/v1/disputes/DSP-000051/approve", json={}).status_code == 401
    assert client.post("/api/v1/disputes/DSP-000051/override", json={}).status_code == 401
    # file
    assert client.post("/api/v1/disputes", json={}).status_code == 401


def test_database_unavailable_returns_error_not_ruling(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000052", ride_id="RIDE-000800",
               planned_km=10.0, actual_km=20.0, quoted_cents=1000, charged_cents=2000)
    reader.available = False
    r = _adjudicate(client, "DSP-000052", rid)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "database_unavailable"
    assert "judge" not in r.json()  # NO ruling


def test_missing_case_is_not_found(client, rid):
    r = _adjudicate(client, "DSP-999999", rid)
    assert r.status_code == 404


def test_below_threshold_case_escalates_with_summary(client, reader, store, rid):
    # A justified >15% deviation lands at confidence 0.72; a contradiction pushes below 0.70.
    case = route_case(reader, store=store, case_id="DSP-000053", ride_id="RIDE-000900",
                      planned_km=10.0, actual_km=13.0, quoted_cents=1000, charged_cents=1300,
                      justified=True)
    # Inject an unverified contradiction on the distance question (I-7 style).
    case.evidence.append(
        type(case.evidence[0])(
            evidence_id="EV-900-U", class_="chat_log", source="rider_submitted",
            visibility="both", verification_status="unverified",
            recorded_at="2026-09-22T06:41:00Z", provenance={},
            payload={"text": "driver took a huge detour", "_question": "distance",
                     "_contradicts_verified": True},
        )
    )
    body = _adjudicate(client, "DSP-000053", rid).json()
    assert body["status"] == "escalated"
    summary = body["judge"]["escalation"]["human_review_summary"]
    assert "QUESTION TO DECIDE" in summary and "RIDER ARGUED" in summary
