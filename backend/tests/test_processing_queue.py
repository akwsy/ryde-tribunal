from tests.fixtures.cases import route_case


def test_processing_claim_is_visible_and_cannot_be_claimed_twice(client, reader, store):
    route_case(reader, store=store, case_id="DSP-009950", ride_id="RIDE-009950",
               planned_km=8.0, actual_km=9.0, quoted_cents=1200, charged_cents=1200)

    assert store.claim_case_processing("DSP-009950") is True
    assert store.claim_case_processing("DSP-009950") is False

    detail = client.get("/api/v1/disputes/DSP-009950")
    assert detail.status_code == 200
    assert detail.json()["status"] == "processing"

    listing = client.get("/api/v1/disputes", params={"limit": 200})
    summary = next(item for item in listing.json()["items"] if item["case_id"] == "DSP-009950")
    assert summary["status"] == "processing"

    assert store.reset_processing_cases() == 1
    assert store.get_case_status("DSP-009950") == "queued"
