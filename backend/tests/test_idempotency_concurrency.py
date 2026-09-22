"""Idempotency is CONCURRENCY-safe (contract §2, brief §7).

Two SIMULTANEOUS adjudications with the same Idempotency-Key must produce ONE ruling — tested
with real threads, not sequential calls. A repeated key with a DIFFERENT body is 409.
"""

from __future__ import annotations

import threading

from tests.fixtures.cases import route_case


def test_concurrent_same_key_produces_one_ruling(client, reader, store, rid):
    route_case(reader, case_id="DSP-000045", ride_id="RIDE-1",
               planned_km=10.0, actual_km=20.0, quoted_cents=1000, charged_cents=2000)

    results: list[dict] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def fire():
        try:
            barrier.wait()  # release both threads as simultaneously as possible
            r = client.post(
                "/api/v1/disputes/DSP-000045/adjudicate",
                headers={"X-Reviewer-Id": rid, "Idempotency-Key": "same-key"},
            )
            results.append(r.json())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=fire) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=40)

    assert not errors, errors
    assert len(results) == 2
    # Exactly one case_id, one ruling — the second caller got the first's result.
    case_ids = {r["case_id"] for r in results}
    assert case_ids == {"DSP-000045"}
    rulings = {r["judge"]["ruling_type"] for r in results}
    assert len(rulings) == 1
    # Only ONE model-work persistence happened for the case (one adjudication ran), recorded
    # in the backend's own store (tribunal.model_work_*), not the read-only reader.
    assert len(store.get_model_work("DSP-000045")) == 1


def test_same_key_different_body_is_conflict(client, reader, rid):
    route_case(reader, case_id="DSP-000045", ride_id="RIDE-1",
               planned_km=10.0, actual_km=20.0, quoted_cents=1000, charged_cents=2000)
    route_case(reader, case_id="DSP-000046", ride_id="RIDE-2",
               planned_km=10.0, actual_km=20.0, quoted_cents=1000, charged_cents=2000)
    first = client.post("/api/v1/disputes/DSP-000045/adjudicate",
                        headers={"X-Reviewer-Id": rid, "Idempotency-Key": "k1"})
    assert first.status_code == 200
    # Same key, different case_id (different body) → conflict.
    second = client.post("/api/v1/disputes/DSP-000046/adjudicate",
                         headers={"X-Reviewer-Id": rid, "Idempotency-Key": "k1"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"
