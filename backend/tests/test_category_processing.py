from unittest.mock import Mock
import base64


def test_reserved_review_categories_run_evidence_triage_without_provider_calls(
    client, container, store, rid
):
    container.provider.complete = Mock(wraps=container.provider.complete)
    for category in ("property_damage", "safety_incident", "lost_item", "conduct_complaint"):
        filed = client.post("/api/v1/disputes", headers={"X-Reviewer-Id": rid}, json={
            "category": category, "ride_id": "RIDE-000001", "filed_by": "rider",
            "subject": f"Review {category}", "description": "Please investigate this report.",
            "category_details": {"incident_timing": "2026-10-14T12:00:00+08:00"},
        })
        assert filed.status_code == 201
        case_id = filed.json()["case_id"]
        case = store.get_filed_case(case_id)
        assert case.category_details["incident_timing"] == "2026-10-14T12:00:00+08:00"

        result = client.post(f"/api/v1/disputes/{case_id}/adjudicate",
                             headers={"X-Reviewer-Id": rid})
        assert result.status_code == 200
        body = result.json()
        assert body["status"] == "pending_review"
        assert body["judge"] is None
        assert body["model_proposed_ruling"] is None
        assert body["triage"]["automated"] is True
        assert body["triage"]["final_decision_required"] is True
        assert body["triage"]["next_steps"]
        assert any(event["event"] == "evidence_assembled" for event in body["trace"])

    container.provider.complete.assert_not_called()


def test_category_details_reject_non_object(client, rid):
    response = client.post("/api/v1/disputes", headers={"X-Reviewer-Id": rid}, json={
        "category": "fare_calculation", "ride_id": "RIDE-000001", "filed_by": "rider",
        "subject": "Fare query", "description": "Check the fare", "category_details": ["invalid"],
    })
    assert response.status_code == 422


def test_party_attachment_is_stored_unverified_and_downloadable(client, store, rid):
    content = b"%PDF-1.4\nsynthetic evidence"
    response = client.post("/api/v1/disputes", headers={"X-Reviewer-Id": rid}, json={
        "category": "property_damage", "ride_id": "RIDE-000001", "filed_by": "rider",
        "subject": "Cleaning receipt", "description": "Receipt attached for review.",
        "attachments": [{"file_name": "receipt.pdf", "media_type": "application/pdf",
                         "data_base64": base64.b64encode(content).decode()}],
    })
    assert response.status_code == 201
    case = store.get_filed_case(response.json()["case_id"])
    ref = case.evidence[0]
    assert ref.verification_status == "unverified"
    assert ref.payload["file_name"] == "receipt.pdf"
    triage = client.post(f"/api/v1/disputes/{case.case_id}/adjudicate",
                         headers={"X-Reviewer-Id": rid})
    assert triage.status_code == 200
    assert ref.evidence_id in triage.json()["triage"]["unverified_evidence_ids"]
    evidence = client.get(f"/api/v1/evidence/{ref.evidence_id}")
    assert evidence.status_code == 200
    assert evidence.json()["verification"]["status"] == "unverified"
    downloaded = client.get(f"/api/v1/evidence/{ref.evidence_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["x-content-type-options"] == "nosniff"


def test_party_attachment_rejects_mismatched_signature(client, rid):
    response = client.post("/api/v1/disputes", headers={"X-Reviewer-Id": rid}, json={
        "category": "lost_item", "ride_id": "RIDE-000001", "filed_by": "rider",
        "subject": "Photo", "description": "Attached image.",
        "attachments": [{"file_name": "photo.png", "media_type": "image/png",
                         "data_base64": base64.b64encode(b"not a PNG").decode()}],
    })
    assert response.status_code == 422
