from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.metrics_helpers import _timeseries_points
from app.persistence.reader import ArchiveHistoryRecord, CaseRecord
from app.persistence.store import ResultStore


@pytest.fixture
def phase1_api(container):
    store = ResultStore()
    container.store = store
    client = TestClient(create_app(container))
    client.app.state.archive_reader = container.reader
    return client, store


def _case(case_id: str, filed_at: str, *, category: str = "route_deviation",
          filed_by: str = "rider") -> CaseRecord:
    return CaseRecord(
        case_id=case_id, ride_id="RIDE-000123", category=category,
        filed_by=filed_by, subject="subject", description="description",
        filed_at=filed_at,
    )


def _result(case_id: str, status: str, *, provider_kind: str = "deterministic-mock",
            escalation: bool = False) -> dict:
    return {
        "case_id": case_id,
        "status": status,
        "urgency": 0.0,
        "synthetic_reasoning": provider_kind == "deterministic-mock",
        "judge": {
            "confidence": 0.91,
            "ruling_type": "refund",
            "provider": {"kind": provider_kind, "display_name": "Gemini"},
            "escalation": {"escalated": escalation},
        },
    }


def test_unadjudicated_filing_appears_in_list_and_metrics(phase1_api, rid):
    client, _store = phase1_api
    filed = client.post(
        "/api/v1/disputes", headers={"X-Reviewer-Id": rid},
        json={"category": "route_deviation", "ride_id": "RIDE-000123",
              "filed_by": "driver", "subject": "Review", "description": "Please review."},
    )
    assert filed.status_code == 201
    case_id = filed.json()["case_id"]

    listed = client.get("/api/v1/disputes").json()["items"]
    item = next(row for row in listed if row["case_id"] == case_id)
    assert item["status"] == "queued"
    assert item["filed_by"] == "driver"
    assert item["case_source"] == "live"
    assert item["provider"] is None
    assert item["created_at"]

    date = item["created_at"][:10]
    metrics = client.get(
        "/api/v1/metrics/overview", params={"from": date, "to": date}
    )
    assert metrics.status_code == 200
    assert metrics.json()["filed"] >= 1


def test_archive_disputes_are_visible_and_contribute_to_dashboard_metrics(phase1_api):
    client, _store = phase1_api
    reader = client.app.state.archive_reader
    reader.archive.extend([
        ArchiveHistoryRecord(
            archive_case_id="DSP-100001", archive_ride_id="RIDE-900001",
            category="fare_calculation", subject="Past fare dispute", filed_by="rider",
            created_at="2026-09-03T04:00:00Z", policy_version="policy-1",
            verdict="refund", ruling_type="refund", recommended_action="Refund S$5",
            amount_cents=500, currency="SGD", confidence=0.92,
            decision_origin="human", human_reviewed=True,
            rulings=[
                {"stage": "model_proposed", "verdict": "refund", "ruling_type": "refund",
                 "recommended_action": "Refund S$4", "amount_cents": 400, "currency": "SGD",
                 "confidence": 0.92, "decision_origin": "agent", "decided_at": "2026-09-03T05:00:00Z"},
                {"stage": "reviewer_approved", "verdict": "refund", "ruling_type": "refund",
                 "recommended_action": "Refund S$5", "amount_cents": 500, "currency": "SGD",
                 "confidence": 0.95, "decision_origin": "human", "decided_at": "2026-09-03T06:00:00Z"},
            ],
        ),
        ArchiveHistoryRecord(
            archive_case_id="DSP-100002", archive_ride_id="RIDE-900002",
            category="route_deviation", subject="Model resolved route dispute", filed_by="driver",
            created_at="2026-09-03T05:00:00Z", policy_version="policy-1",
            verdict="no_action", ruling_type="no_action", recommended_action="No action",
            amount_cents=0, currency="SGD", confidence=0.91,
            decision_origin="agent", human_reviewed=False,
            rulings=[{"stage": "model_proposed", "verdict": "no_action", "ruling_type": "no_action",
                      "recommended_action": "No action", "amount_cents": 0, "currency": "SGD",
                      "confidence": 0.91, "decision_origin": "agent", "decided_at": "2026-09-03T06:00:00Z"}],
        ),
    ])

    assert len(reader.list_archive_disputes()) == 2
    archive = client.get("/api/v1/archive/disputes")
    assert archive.status_code == 200, archive.text
    assert archive.json()["statistics"] == {
        "total": 2, "reviewer_approved": 1, "model_only": 1, "escalated": 0,
        "ongoing": 0,
    }
    assert {item["archive_ride_id"] for item in archive.json()["items"]} == {
        "RIDE-900001", "RIDE-900002",
    }
    assert archive.json()["items"][0]["rulings"][1]["stage"] == "reviewer_approved"

    metrics = client.get("/api/v1/metrics/overview", params={
        "from": "2026-09-03", "to": "2026-09-03",
    })
    assert metrics.status_code == 200
    assert metrics.json()["filed"] == 2
    assert metrics.json()["auto_resolved"] == 1
    assert metrics.json()["human_intervention"] == 1

    cases = client.get("/api/v1/disputes")
    by_id = {item["case_id"]: item for item in cases.json()["items"]}
    assert set(by_id) == {"DSP-100001", "DSP-100002"}
    assert {item["case_source"] for item in by_id.values()} == {"archive"}


def test_dashboard_aggregates_every_status_and_archive_record(phase1_api):
    """Filed totals and category charts count resolved, open, and archived cases alike."""
    client, store = phase1_api
    filed_at = "2026-09-03T04:00:00Z"
    for case_id, status, category in (
        ("DSP-000851", "resolved", "route_deviation"),
        ("DSP-000852", "escalated", "fare_calculation"),
        ("DSP-000853", "queued", "no_show_charge"),
    ):
        case = _case(case_id, filed_at, category=category)
        store.save_filed_case(case)
        if status != "queued":
            store.save_case_result(_result(
                case_id, status, escalation=(status == "escalated")
            ))

    client.app.state.archive_reader.archive.append(ArchiveHistoryRecord(
        archive_case_id="DSP-100003", archive_ride_id="RIDE-900003",
        category="conduct_complaint", subject="Archived resolved case", filed_by="rider",
        created_at=filed_at, policy_version="policy-1", verdict="no_action",
        ruling_type="no_action", recommended_action="No action", amount_cents=0,
        currency="SGD", confidence=0.91, decision_origin="agent", human_reviewed=False,
        rulings=[{"stage": "model_proposed", "verdict": "no_action",
                  "ruling_type": "no_action", "recommended_action": "No action",
                  "amount_cents": 0, "currency": "SGD", "confidence": 0.91,
                  "decision_origin": "agent", "decided_at": filed_at}],
    ))
    client.app.state.metrics_bucket_selector = lambda _days: "day"
    params = {"from": "2026-09-03", "to": "2026-09-03"}

    overview = client.get("/api/v1/metrics/overview", params=params)
    assert overview.status_code == 200
    assert overview.json()["filed"] == 4

    breakdown = client.get("/api/v1/metrics/breakdown", params=params)
    assert breakdown.status_code == 200
    assert sum(item["count"] for item in breakdown.json()["slices"]) == 4

    timeseries = client.get("/api/v1/metrics/timeseries", params=params)
    assert timeseries.status_code == 200
    assert sum(item["count"] for item in timeseries.json()["points"][0]["series"]) == 4

    mixed = client.get("/api/v1/disputes")
    assert mixed.status_code == 200
    assert {item["case_source"] for item in mixed.json()["items"]} == {"live", "archive"}


def test_overview_uses_inclusive_singapore_filing_dates(phase1_api):
    client, store = phase1_api
    # 15:59:59Z is 23:59:59 in Singapore; 16:00Z is midnight next day.
    store.save_filed_case(_case("DSP-000801", "2026-09-02T15:59:59Z"))
    store.save_case_result(_result("DSP-000801", "resolved"))
    store.save_filed_case(_case("DSP-000802", "2026-09-02T16:00:00Z"))
    store.save_case_result(_result("DSP-000802", "escalated", escalation=True))
    store.save_filed_case(_case("DSP-000803", "2026-09-02T01:00:00Z", category="safety_incident"))

    first_day = client.get("/api/v1/metrics/overview", params={
        "from": "2026-09-02", "to": "2026-09-02",
    }).json()
    assert first_day["filed"] == 2
    assert first_day["auto_resolved"] == 1
    assert first_day["human_intervention"] == 0

    second_day = client.get("/api/v1/metrics/overview", params={
        "from": "2026-09-03", "to": "2026-09-03",
    }).json()
    assert second_day["filed"] == 1
    assert second_day["auto_resolved"] == 0
    assert second_day["human_intervention"] == 1


def test_breakdown_supports_dimensions_and_unknown_provider(phase1_api):
    client, store = phase1_api
    store.save_filed_case(_case("DSP-000811", "2026-09-03T04:00:00Z", filed_by="driver"))
    store.save_filed_case(_case("DSP-000812", "2026-09-03T05:00:00Z", category="safety_incident"))
    store.save_case_result({"case_id": "DSP-000812", "status": "pending_review", "judge": None})
    params = {"from": "2026-09-03", "to": "2026-09-03"}

    categories = client.get("/api/v1/metrics/breakdown", params=params).json()["slices"]
    assert {slice_["key"]: slice_["count"] for slice_ in categories} == {
        "route_deviation": 1, "safety_incident": 1,
    }
    providers = client.get("/api/v1/metrics/breakdown", params={**params, "by": "provider"}).json()
    assert {slice_["key"]: slice_["count"] for slice_ in providers["slices"]} == {
        "unknown": 2,
    }
    filed_by = client.get("/api/v1/metrics/breakdown", params={**params, "by": "filed_by"}).json()
    assert {slice_["key"]: slice_["count"] for slice_ in filed_by["slices"]} == {
        "driver": 1, "rider": 1,
    }


def test_case_summary_provider_is_vendor_only_or_local_deterministic(phase1_api):
    client, store = phase1_api
    local = _case("DSP-000821", "2026-09-03T04:00:00Z")
    llm = _case("DSP-000822", "2026-09-03T05:00:00Z")
    store.save_filed_case(local)
    store.save_case_result(_result(local.case_id, "resolved"))
    store.save_filed_case(llm)
    store.save_case_result(_result(llm.case_id, "resolved", provider_kind="llm"))
    items = {item["case_id"]: item for item in client.get("/api/v1/disputes").json()["items"]}
    assert items[local.case_id]["provider"] == "local deterministic"
    assert items[llm.case_id]["provider"] == "Gemini"


def test_breakdown_rejects_unknown_dimension_and_invalid_date_range(phase1_api):
    client, _store = phase1_api
    bad_dimension = client.get("/api/v1/metrics/breakdown", params={
        "from": "2026-09-01", "to": "2026-09-02", "by": "review_path",
    })
    assert bad_dimension.status_code == 422
    bad_range = client.get("/api/v1/metrics/overview", params={
        "from": "2026-09-03", "to": "2026-09-02",
    })
    assert bad_range.status_code == 422


def test_timeseries_aggregation_groups_by_sunday_start_and_filing_date():
    rows = [
        {"case": _case("DSP-000831", "2026-09-06T04:00:00Z"), "result": None},  # Sun SG
        {"case": _case("DSP-000832", "2026-09-06T16:00:00Z", category="no_show_charge"), "result": None},
        {"case": _case("DSP-000833", "2026-09-07T03:00:00Z", filed_by="driver"), "result": None},
    ]
    from datetime import datetime, timezone

    points = _timeseries_points(
        rows,
        datetime.fromisoformat("2026-09-05T16:00:00+00:00"),
        datetime.fromisoformat("2026-09-08T16:00:00+00:00"),
        "category", "week",
    )
    assert points == [{
        "date": "2026-09-06",
        "series": [
            {"key": "no_show_charge", "count": 1},
            {"key": "route_deviation", "count": 2},
        ],
    }]


def test_timeseries_endpoint_keeps_bucket_cutoff_unconfigured_until_confirmed(phase1_api):
    client, _store = phase1_api
    response = client.get("/api/v1/metrics/timeseries", params={
        "from": "2026-09-01", "to": "2026-09-30",
    })
    assert response.status_code == 503
    assert "thresholds are not configured" in response.json()["error"]["message"]


def test_timeseries_endpoint_uses_injected_bucket_policy_and_group_dimension(phase1_api):
    client, store = phase1_api
    store.save_filed_case(_case("DSP-000841", "2026-09-06T04:00:00Z"))
    store.save_filed_case(_case("DSP-000842", "2026-09-06T16:00:00Z", category="no_show_charge"))
    client.app.state.metrics_bucket_selector = lambda _days: "week"

    response = client.get("/api/v1/metrics/timeseries", params={
        "from": "2026-09-06", "to": "2026-09-07", "group_by": "category",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["granularity"] == "week"
    assert body["points"] == [{
        "date": "2026-09-06",
        "series": [
            {"key": "no_show_charge", "count": 1},
            {"key": "route_deviation", "count": 1},
        ],
    }]
