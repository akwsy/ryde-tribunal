from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _prose_rules():
    text = (ROOT / "docs/03-mock-policy.md").read_text()
    return dict(re.findall(r"\*\*(RP-[A-Z]+-\d{3})\.\*\*\s+(.+?)(?=\n\n|\n\*\*|\Z)", text, re.S))


def test_loaded_policy_is_canonical_seed_and_matches_prose():
    policy = json.loads((ROOT / "database/seed/policy/ryde-policy-0.1.0.json").read_text())
    loaded = {r["id"]: r["text"] for r in policy["rules"]}
    prose = {key: " ".join(value.split()) for key, value in _prose_rules().items()}
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


def test_seeded_no_show_case_travels_through_public_api(client):
    case_id, result = _adjudicate(client, "no_show", "RIDE-000002")
    assert result["case_id"] == case_id
    assert result["category"] == "no_show"
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
