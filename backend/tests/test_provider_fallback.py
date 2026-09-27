from __future__ import annotations

from app.api.app import create_app
from app.api.container import build_container
from app.providers.base import Completion, ProviderMeta, ProviderUnavailable
from app.providers.deterministic_mock import DeterministicMockProvider
from tests.conftest import make_settings


class FailAfterOneLLMCall:
    """Simulates a successful first component followed by an LLM outage."""

    meta = ProviderMeta(kind="llm", model="test-llm")

    def __init__(self):
        self.calls = 0
        self.delegate = DeterministicMockProvider("partial-llm-proxy")

    def complete(self, prompt: dict, response_schema: dict) -> Completion:
        self.calls += 1
        if self.calls == 1:
            return self.delegate.complete(prompt, response_schema)
        raise ProviderUnavailable("simulated outage")


class MalformedLLMResponse:
    meta = ProviderMeta(kind="llm", model="test-llm")

    def __init__(self):
        self.calls = 0

    def complete(self, prompt: dict, response_schema: dict) -> Completion:
        self.calls += 1
        return Completion(data={"argument": "Malformed response", "claims": [
            {"text": "A claim", "citations": [{
                "evidence_id": [], "field_path": "quoted_fare_cents",
                "observed_value": 1000, "supports": "claim-1",
            }]}
        ], "policy_references": [], "rejected_evidence": []}, provider=self.meta)


class FailOnFraudAssessment:
    """Ensures the newly added model role is included in whole-case fallback."""

    meta = ProviderMeta(kind="llm", model="test-llm")

    def __init__(self):
        self.delegate = DeterministicMockProvider("test-llm-proxy")

    def complete(self, prompt: dict, response_schema: dict) -> Completion:
        if prompt.get("role") == "fraud_detector":
            raise ProviderUnavailable("simulated fraud-model outage")
        return self.delegate.complete(prompt, response_schema)


def test_llm_failure_restarts_whole_case_with_deterministic_provider(reader, rid):
    provider = FailAfterOneLLMCall()
    container = build_container(
        reader=reader, settings=make_settings(), provider=provider  # type: ignore[arg-type]
    )
    # Use FastAPI's test client, keeping the normal public filing/adjudication flow.
    from fastapi.testclient import TestClient

    client = TestClient(create_app(container))
    filed = client.post(
        "/api/v1/disputes",
        headers={"X-Reviewer-Id": rid},
        json={
            "category": "route_deviation",
            "ride_id": "RIDE-000001",
            "filed_by": "rider",
            "subject": "Route dispute",
            "description": "The route was longer than expected.",
        },
    )
    case_id = filed.json()["case_id"]

    result = client.post(
        f"/api/v1/disputes/{case_id}/adjudicate", headers={"X-Reviewer-Id": rid}
    ).json()

    assert provider.calls == 2  # one partial completion, then the failure
    assert result["synthetic_reasoning"] is True
    assert result["advocates"]["rider"]["provider"]["kind"] == "deterministic-mock"
    assert result["advocates"]["driver"]["provider"]["kind"] == "deterministic-mock"
    assert result["judge"]["provider"]["kind"] == "deterministic-mock"
    work = container.store.get_model_work(case_id)
    assert len(work) == 1
    assert work[0]["advocates"]["rider"]["provider"]["kind"] == "deterministic-mock"


def test_malformed_llm_output_restarts_with_deterministic_provider(reader, rid):
    provider = MalformedLLMResponse()
    container = build_container(
        reader=reader, settings=make_settings(), provider=provider  # type: ignore[arg-type]
    )
    from fastapi.testclient import TestClient

    client = TestClient(create_app(container))
    case_id = client.post(
        "/api/v1/disputes",
        headers={"X-Reviewer-Id": rid},
        json={"category": "route_deviation", "ride_id": "RIDE-000001",
              "filed_by": "rider", "subject": "Route dispute", "description": "Test."},
    ).json()["case_id"]
    result = client.post(
        f"/api/v1/disputes/{case_id}/adjudicate", headers={"X-Reviewer-Id": rid}
    ).json()

    assert provider.calls == 1
    assert result["synthetic_reasoning"] is True
    assert result["judge"]["provider"]["kind"] == "deterministic-mock"


def test_fraud_model_outage_restarts_whole_case_with_deterministic_provider(reader, rid):
    provider = FailOnFraudAssessment()
    container = build_container(
        reader=reader, settings=make_settings(), provider=provider  # type: ignore[arg-type]
    )
    from fastapi.testclient import TestClient

    client = TestClient(create_app(container))
    case_id = client.post(
        "/api/v1/disputes", headers={"X-Reviewer-Id": rid},
        json={"category": "route_deviation", "ride_id": "RIDE-000001",
              "filed_by": "rider", "subject": "Route dispute", "description": "Test."},
    ).json()["case_id"]
    result = client.post(
        f"/api/v1/disputes/{case_id}/adjudicate", headers={"X-Reviewer-Id": rid}
    ).json()

    assert result["synthetic_reasoning"] is True
    assert result["judge"]["provider"]["display_name"] == "local deterministic"
