from __future__ import annotations

from app.api.app import create_app
from app.api.container import build_container
from app.providers.base import Completion, ProviderMeta, ProviderUnavailable
from app.providers.deterministic_mock import DeterministicMockProvider
from tests.conftest import make_settings


class FailOnJudgeCall:
    """Simulates a live Judge outage after the deterministic helper rounds."""

    meta = ProviderMeta(kind="llm", model="test-llm")

    def __init__(self):
        self.calls = 0
    def complete(self, prompt: dict, response_schema: dict) -> Completion:
        self.calls += 1
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


class RecordingProvider:
    """Records that uncertainty review makes one model call, for the Judge only."""

    meta = ProviderMeta(kind="llm", model="test-llm")

    def __init__(self):
        self.delegate = DeterministicMockProvider("test-llm-proxy")
        self.roles = []

    def complete(self, prompt: dict, response_schema: dict) -> Completion:
        self.roles.append(prompt.get("role"))
        return self.delegate.complete(prompt, response_schema)


def test_llm_failure_restarts_whole_case_with_deterministic_provider(reader, rid, monkeypatch):
    import app.orchestration.orchestrator as orchestration
    monkeypatch.setattr(orchestration, "model_review_blockers", lambda *args, **kwargs: [])
    provider = FailOnJudgeCall()
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

    assert provider.calls == 1
    assert result["synthetic_reasoning"] is True
    assert result["advocates"]["rider"]["provider"]["kind"] == "rules-engine"
    assert result["advocates"]["driver"]["provider"]["kind"] == "rules-engine"
    assert result["judge"]["provider"]["kind"] == "deterministic-mock"
    assert result["judge"]["escalation"]["escalated"] is True
    assert any(item["event"] == "human_review_required" for item in result["trace"])
    fallback = next(event for event in result["trace"] if event["event"] == "fallback")
    assert "provider unavailable" in fallback["summary"]
    assert "live Judge output was not accepted" in fallback["summary"]
    work = container.store.get_model_work(case_id)
    assert len(work) == 1
    assert work[0]["advocates"]["rider"]["provider"]["kind"] == "rules-engine"


def test_malformed_llm_output_restarts_with_deterministic_provider(reader, rid, monkeypatch):
    import app.orchestration.orchestrator as orchestration
    monkeypatch.setattr(orchestration, "model_review_blockers", lambda *args, **kwargs: [])
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
    assert result["judge"]["escalation"]["escalated"] is True
    assert any(item["event"] == "human_review_required" for item in result["trace"])


def test_uncertain_case_calls_only_judge_model_after_helper_checks(reader, rid, monkeypatch):
    import app.orchestration.orchestrator as orchestration
    monkeypatch.setattr(orchestration, "model_review_blockers", lambda *args, **kwargs: [])
    provider = RecordingProvider()
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

    assert provider.roles == ["judge"]
    events = [item["event"] for item in result["trace"]]
    assert events.count("review_round") == 3
    assert events.index("gemini_escalation") < events.index("ruling_proposed")
