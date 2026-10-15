"""Shared pytest fixtures using the deterministic mock and canonical current policy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import build_container
from app.settings import Settings
from tests.fixtures.reader import FixtureReader

_POLICY = Path(__file__).resolve().parents[2] / "database" / "seed" / "policy" / "ryde-policy-0.1.2.json"


def make_settings(**overrides) -> Settings:
    base = dict(
        model_provider="deterministic_mock",
        model_name="ryde-mock-judge-1",
        # These legacy orchestration tests preserve their original policy snapshot.
        # Current-policy acceptance lives in test_submission_policy.py.
        policy_version="ryde-policy-0.1.2",
        policy_path=str(_POLICY),
        currency="SGD",
        escalation_confidence_threshold=0.70,
        high_impact_amount_cents=2500,
        goodwill_cap_cents=1500,
    )
    base.update(overrides)
    # Never let backend/.env wire tests to the persistent local database. Tests
    # inject FixtureReader and must use the in-memory ResultStore unless a test
    # explicitly provisions a disposable database.
    return Settings(_env_file=None, **base)


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
