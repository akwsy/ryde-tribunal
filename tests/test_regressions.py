from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _prose_rules():
    text = (ROOT / "docs/03-mock-policy.md").read_text()
    return dict(re.findall(r"\*\*(RP-[A-Z]+-\d{3})\.\*\*\s+(.+?)(?=\n\n|\n\*\*|\Z)", text, re.S))


def _normalize_policy_text(value):
    return " ".join(value.replace("**", "").replace("*", "").replace("`", "").replace("≥", ">=").replace("≤", "<=").split())


def test_loaded_policy_is_canonical_seed_and_matches_prose():
    # The prose describes the current policy. Historical policy versions are immutable
    # snapshots and intentionally do not track later safety and fraud decisions.
    policy = json.loads((ROOT / "database/seed/policy/ryde-policy-0.1.2.json").read_text())
    loaded = {r["id"]: r["text"] for r in policy["rules"]}
    prose = {key: _normalize_policy_text(value) for key, value in _prose_rules().items()}
    loaded = {key: _normalize_policy_text(value) for key, value in loaded.items()}
    # The prose appends this explanatory fraud note to RP-ESC-003; the machine rule
    # already encodes that fraud alone is not an escalation trigger via its criteria.
    fraud_note = " Fraud risk informs the Judge's ruling and does not by itself trigger escalation."
    prose["RP-ESC-003"] = prose["RP-ESC-003"].removesuffix(fraud_note)
    assert set(loaded) == set(prose)
    mismatches = {key: (loaded.get(key), prose[key]) for key in prose if loaded.get(key) != prose[key]}
    assert not mismatches, f"canonical policy divergence ({len(mismatches)} rules): {mismatches}"


def _adjudicate(client, category, ride_id):
    filed = client.post("/api/v1/disputes", headers={"X-Reviewer-Id": "REV-QA"}, json={
        "category": category, "ride_id": ride_id, "filed_by": "rider",
        "subject": "QA case", "description": "QA integration case"})
    assert filed.status_code == 201, filed.text
    case_id = filed.json()["case_id"]
    result = client.post(f"/api/v1/disputes/{case_id}/adjudicate", headers={"X-Reviewer-Id": "REV-QA"})
    assert result.status_code == 200, result.text
    return case_id, result.json()


def test_seeded_route_case_has_evidence_trace_and_positive_remedy(client):
    case_id, result = _adjudicate(client, "route_deviation", "RIDE-000001")
    assert result["judge"]["evidence_references"]
    assert all(claim["citations"] for side in result["advocates"].values() for claim in side["claims"])
    for evidence_id in result["judge"]["evidence_references"]:
        evidence = client.get(f"/api/v1/evidence/{evidence_id}")
        assert evidence.status_code == 200
        assert evidence.json()["case_id"] == case_id
    if result["judge"]["ruling_type"] in {"refund", "compensation"}:
        assert result["judge"]["recommended_action"]["amount"]["amount_cents"] > 0
    assert result["synthetic_reasoning"] is True


def test_every_citation_is_explicitly_valid_and_evidence_ids_are_well_formed(client):
    _, result = _adjudicate(client, "route_deviation", "RIDE-000001")
    ids = set(result["judge"]["evidence_references"])
    for side in result["advocates"].values():
        for claim in side["claims"]:
            for citation in claim["citations"]:
                assert "valid" in citation
                assert citation["valid"] is True
                assert re.fullmatch(r"EV-\d{6}", citation["evidence_id"])
                ids.add(citation["evidence_id"])
    assert ids


def test_advocates_are_party_specific_and_do_not_share_near_identical_arguments(client):
    _, result = _adjudicate(client, "route_deviation", "RIDE-000001")
    rider = result["advocates"]["rider"]["argument"].lower()
    driver = result["advocates"]["driver"]["argument"].lower()
    assert rider != driver
    assert SequenceMatcher(None, rider, driver).ratio() < 0.90
    assert any(word in rider for word in ("rider", "refund", "overcharg"))
    assert any(word in driver for word in ("driver", "justif", "dispute"))


def test_live_facts_have_no_outcome_fields_and_archive_rejects_live_id(client, reader):
    _, result = _adjudicate(client, "route_deviation", "RIDE-000001")
    forbidden = re.compile(r"expected|verdict|outcome|resolution|fault|ground.?truth|correct|is_valid|refund_granted", re.I)
    assert not any(forbidden.search(key) for key in result["case_facts"])
    with __import__("pytest").raises(Exception):
        reader.get_archive_case("DSP-000045")


def test_zero_remedy_cannot_be_a_refund_or_compensation(client):
    _, result = _adjudicate(client, "no_show_charge", "RIDE-000002")
    action = result["judge"]["recommended_action"]
    amount = action.get("amount", {}).get("amount_cents", 0)
    if amount == 0:
        assert result["judge"]["ruling_type"] not in {"refund", "compensation"}
        assert result["status"] in {"escalated", "pending_review", "resolved"}


def test_seeded_no_show_case_travels_through_public_api(client):
    case_id, result = _adjudicate(client, "no_show_charge", "RIDE-000002")
    assert result["case_id"] == case_id
    assert result["category"] == "no_show_charge"
    assert result["advocates"]["rider"]["claims"]
    assert result["judge"]["evidence_references"]


def test_database_unavailable_returns_error_and_never_a_ruling(reader, client):
    reader.available = False
    filed = client.post("/api/v1/disputes", headers={"X-Reviewer-Id": "REV-QA"}, json={"category":"route_deviation", "ride_id":"RIDE-000001", "filed_by":"rider", "subject":"x", "description":"x"})
    response = client.post(f"/api/v1/disputes/{filed.json()['case_id']}/adjudicate", headers={"X-Reviewer-Id":"REV-QA"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "judge" not in response.json()


def test_human_override_preserves_original_ruling_and_history(client):
    case_id, original = _adjudicate(client, "route_deviation", "RIDE-000001")
    override = client.post(f"/api/v1/disputes/{case_id}/override", headers={"X-Reviewer-Id":"HUMAN-1"}, json={"ruling_type":"no_action", "recommended_action":{"description":"manual review"}, "reason_code":"evidence_misweighted", "rationale":"QA override"})
    assert override.status_code == 200
    body = override.json()
    assert body["status"] == "overridden"
    assert body["judge"] == original["judge"]
    assert any(event["event"] == "overridden" and event["actor_id"] == "HUMAN-1" for event in body["case_history"])
