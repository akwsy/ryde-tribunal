from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.persistence.reader import ArchiveCase, CaseRecord, RideRecord
from app.persistence.store import ResultStore


def _archive_record(case_id: str = "DSP-900001") -> ArchiveCase:
    return ArchiveCase(
        archive_case_id=case_id,
        archive_ride_id="RIDE-900001",
        category="fare_calculation",
        ruling_type="refund",
        recommended_action="Refund S$5",
        confidence=0.91,
        decision_origin="human",
        policy_version="policy-1",
        was_overridden=True,
        rulings=[
            {
                "stage": "model_proposed",
                "decision": {
                    "verdict": "no_action",
                    "ruling_type": "no_action",
                    "recommended_action_description": "No action",
                    "recommended_amount": {"amount_cents": 0, "currency": "SGD"},
                    "confidence": 0.8,
                    "decision_origin": "agent",
                    "decided_at": "2026-08-01T12:00:00Z",
                },
            },
            {
                "stage": "reviewer_approved",
                "decision": {
                    "verdict": "refund",
                    "ruling_type": "refund",
                    "recommended_action_description": "Refund S$5",
                    "recommended_amount": {"amount_cents": 500, "currency": "SGD"},
                    "confidence": 0.91,
                    "decision_origin": "human",
                    "decided_at": "2026-08-01T13:00:00Z",
                },
            },
        ],
        archive_record={
            "archive_case_id": case_id,
            "archive_ride_id": "RIDE-900001",
            "category": "fare_calculation",
            "subject": "Historical fare dispute",
            "filed_by": "rider",
            "created_at": "2026-08-01T11:00:00Z",
            "policy_version": "policy-1",
            "synthetic": True,
            "trip_snapshot": {
                "archive_ride_id": "RIDE-900001",
                "trip_status": "completed",
                "rider": {"archive_user_id": "USR-R-900001"},
                "driver": {"archive_user_id": "USR-D-900001"},
            },
            "filing_user_snapshot": {"archive_user_id": "USR-R-900001"},
            "evidence": [
                {"evidence_id": "EV-900001", "evidence_class": "fare"},
            ],
            "human_review": {
                "human_reviewed": True,
                "rationale": "The fare ledger supports a partial refund.",
                "reason_code": "evidence_misweighted",
            },
            "decision": {
                "verdict": "refund",
                "ruling_type": "refund",
                "recommended_action_description": "Refund S$5",
                "recommended_amount": {"amount_cents": 500, "currency": "SGD"},
                "confidence": 0.91,
                "decision_origin": "human",
                "decided_at": "2026-08-01T13:00:00Z",
            },
        },
    )


def test_get_dispute_can_open_archive_case_through_archive_scoped_lookup(container):
    container.store = ResultStore()
    container.reader.archive.append(_archive_record())
    client = TestClient(create_app(container))

    response = client.get("/api/v1/disputes/DSP-900001")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case_id"] == "DSP-900001"
    assert body["case_source"] == "archive"
    assert body["ride_id"] == "RIDE-900001"
    assert body["status"] == "resolved"
    assert body["judge"] is None
    assert body["advocates"] is None
    assert body["model_proposed_ruling"]["ruling_type"] == "no_action"
    assert body["reviewer_approved_ruling"]["ruling_type"] == "refund"
    assert body["case_facts"]["archived_trip_snapshot"]["rider"]["archive_user_id"] == "USR-R-900001"
    assert body["case_facts"]["archived_evidence"][0]["evidence_id"] == "EV-900001"


def test_queued_live_case_detail_returns_filing_data_without_adjudicating(container, monkeypatch):
    container.store = ResultStore()
    case = CaseRecord(
        case_id="DSP-900001", ride_id="RIDE-900001", category="fare_calculation",
        filed_by="rider", subject="Live case", description="Unadjudicated",
        claimed_amount_cents=500, currency="SGD", filed_at="2026-08-01T11:00:00Z",
    )
    container.store.save_filed_case(case)
    container.reader.rides[case.ride_id] = RideRecord(
        ride_id=case.ride_id,
        rider_id="USR-R-900001",
        driver_id="USR-D-900001",
        synthetic=True,
    )
    container.store.append_history("DSP-900001", {
        "event": "filed", "actor_type": "reviewer", "actor_id": "REV-001",
        "at": case.filed_at, "payload": {"category": "fare_calculation"},
    })
    container.reader.archive.append(_archive_record())

    def must_not_read_archive(_case_id: str):
        raise AssertionError("live case ID fell through to archive lookup")

    monkeypatch.setattr(container.reader, "get_archive_case", must_not_read_archive)
    client = TestClient(create_app(container))

    response = client.get("/api/v1/disputes/DSP-900001")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case_source"] == "live"
    assert body["case_id"] == case.case_id
    assert body["ride_id"] == case.ride_id
    assert body["category"] == case.category
    assert body["status"] == "queued"
    assert body["synthetic"] is True
    assert body["synthetic_reasoning"] is False
    assert body["case_facts"] == {
        "filing": {
            "filed_by": "rider",
            "subject": "Live case",
            "description": "Unadjudicated",
            "claimed_amount_cents": 500,
            "currency": "SGD",
        },
        "submitted_evidence_ids": [],
    }
    assert body["judge"] is None
    assert body["advocates"] is None
    assert body["model_proposed_ruling"] is None
    assert body["reviewer_approved_ruling"] is None
    assert body["case_history"] == [{
        "event": "filed", "actor_type": "reviewer", "actor_id": "REV-001",
        "at": case.filed_at, "payload": {"category": "fare_calculation"},
    }]


def test_missing_live_or_archive_case_still_returns_not_found(container):
    container.store = ResultStore()
    client = TestClient(create_app(container))

    response = client.get("/api/v1/disputes/DSP-900099")

    assert response.status_code == 404


def test_live_case_result_detail_marks_its_source(container):
    container.store = ResultStore()
    container.store.save_case_result({
        "case_id": "DSP-900002",
        "status": "resolved",
        "judge": None,
    })
    client = TestClient(create_app(container))

    response = client.get("/api/v1/disputes/DSP-900002")

    assert response.status_code == 200, response.text
    assert response.json()["case_source"] == "live"


def test_archive_detail_does_not_enable_live_review_or_adjudication_routes(container):
    container.store = ResultStore()
    container.reader.archive.append(_archive_record())
    client = TestClient(create_app(container))
    headers = {"X-Reviewer-Id": "REV-001"}

    adjudicate = client.post(
        "/api/v1/disputes/DSP-900001/adjudicate", headers=headers
    )
    approve = client.post(
        "/api/v1/disputes/DSP-900001/approve", headers=headers, json={"note": "review"}
    )
    override = client.post(
        "/api/v1/disputes/DSP-900001/override",
        headers=headers,
        json={
            "ruling_type": "no_action",
            "recommended_action": {"description": "No action"},
            "reason_code": "other",
            "rationale": "Historical records are read-only.",
        },
    )

    assert adjudicate.status_code == 404
    assert approve.status_code == 404
    assert override.status_code == 404
    assert container.store.count_filed_cases() == 0
