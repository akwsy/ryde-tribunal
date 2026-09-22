"""Shared pytest fixtures: a wired app + TestClient over a FixtureReader, using the
deterministic_mock provider and the backend fixture policy document (offline, what CI runs).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import build_container
from app.settings import Settings
from tests.fixtures.reader import FixtureReader

_POLICY = (
    Path(__file__).resolve().parent
    / "fixtures" / "policy" / "ryde-policy-0.1.0.json"
)


def make_settings(**overrides) -> Settings:
    base = dict(
        model_provider="deterministic_mock",
        model_name="ryde-mock-judge-1",
        policy_version="ryde-policy-0.1.0",
        policy_path=str(_POLICY),
        currency="SGD",
        escalation_confidence_threshold=0.70,
        high_impact_amount_cents=2500,
        goodwill_cap_cents=1500,
        fraud_risk_escalation_threshold=0.60,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def reader() -> FixtureReader:
    return FixtureReader()


@pytest.fixture
def container(reader):
    return build_container(reader=reader, settings=make_settings())


@pytest.fixture
def app(container):
    return create_app(container)


@pytest.fixture
def store(container):
    return container.store


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def rid() -> str:
    return "REV-001"  # X-Reviewer-Id used across mutating requests
