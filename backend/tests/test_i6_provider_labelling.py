"""I-6 — scripted providers must be labelled as scripted, everywhere.

`provider` is present on every component output and is never absent. When any component ran on
the mock, the ruling carries `synthetic_reasoning: true`.
"""

from __future__ import annotations

from app.providers.base import ProviderMeta
from tests.fixtures.cases import route_case


def _adjudicate(client, case_id, rid):
    return client.post(f"/api/v1/disputes/{case_id}/adjudicate",
                       headers={"X-Reviewer-Id": rid}).json()


def test_provider_present_on_every_component(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000045", ride_id="RIDE-1",
               planned_km=10.0, actual_km=14.0, quoted_cents=1000, charged_cents=1400)
    body = _adjudicate(client, "DSP-000045", rid)
    for side in ("rider", "driver"):
        prov = body["advocates"][side]["provider"]
        assert prov and prov["kind"] and prov["model"]
        assert prov["policy_version"] == "ryde-policy-0.1.2"
    jp = body["judge"]["provider"]
    assert jp and jp["kind"] and jp["model"]


def test_synthetic_reasoning_true_under_mock(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000046", ride_id="RIDE-2",
               planned_km=10.0, actual_km=14.0, quoted_cents=1000, charged_cents=1400)
    body = _adjudicate(client, "DSP-000046", rid)
    assert body["synthetic_reasoning"] is True
    assert body["advocates"]["rider"]["provider"]["kind"] == "rules-engine"
    assert body["judge"]["provider"]["kind"] == "deterministic-mock"


def test_provider_meta_kind_flags_synthetic():
    assert ProviderMeta(kind="deterministic-mock", model="m").is_synthetic is True
    assert ProviderMeta(kind="llm", model="m").is_synthetic is False


def test_synthetic_reasoning_false_when_all_components_are_llm(reader, rid):
    """If every component ran on an llm provider, synthetic_reasoning is False. We simulate an
    llm provider that returns the same structured shape as the mock but labels kind=llm."""
    from app.api.app import create_app
    from app.api.container import build_container
    from app.providers.base import Completion, ProviderMeta
    from app.providers.deterministic_mock import DeterministicMockProvider
    from fastapi.testclient import TestClient
    from tests.conftest import make_settings

    class LabelledLLM:
        def __init__(self):
            self._inner = DeterministicMockProvider(model="pretend-llm")
            self._meta = ProviderMeta(kind="llm", model="pretend-llm")

        @property
        def meta(self):
            return self._meta

        def complete(self, prompt, schema):
            c = self._inner.complete(prompt, schema)
            return Completion(data=c.data, provider=self._meta)

    container = build_container(reader=reader, settings=make_settings(), provider=LabelledLLM())
    route_case(reader, store=container.store, case_id="DSP-000047", ride_id="RIDE-3",
               planned_km=10.0, actual_km=14.0, quoted_cents=1000, charged_cents=1400)
    client = TestClient(create_app(container))
    body = client.post("/api/v1/disputes/DSP-000047/adjudicate",
                       headers={"X-Reviewer-Id": rid}).json()
    assert body["synthetic_reasoning"] is False
    assert body["judge"]["provider"]["kind"] == "llm"
