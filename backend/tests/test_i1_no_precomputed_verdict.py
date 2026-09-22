"""I-1 — the policy engine must not pre-compute the verdict.

Static structural check over the class definitions PLUS a behavioural check that the policy
evaluator's output for a real case carries measurements + rule ids and NOTHING verdict-shaped.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.policy.context import (
    FORBIDDEN_FIELD_RE,
    Measurement,
    PolicyContext,
    PolicyRule,
)
from app.policy import evaluator
from app.policy.loader import load_policy
from tests.conftest import _POLICY

VERDICT_RE = re.compile(
    r"rul(e|ing)_type|verdict|recommend|action|amount|fault|refund", re.IGNORECASE
)


def _policy():
    return load_policy("ryde-policy-0.1.0", explicit_path=str(_POLICY))


def test_policycontext_has_no_verdict_field():
    for cls in (PolicyContext, PolicyRule, Measurement):
        for name in cls.model_fields:
            assert not VERDICT_RE.search(name), f"{cls.__name__}.{name} is verdict-shaped"


def test_policycontext_is_frozen():
    ctx = PolicyContext(policy_version="ryde-policy-0.1.0", category="route_deviation")
    assert ctx.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        ctx.category = "no_show"  # type: ignore[misc]


def test_measurement_rejects_verdict_shaped_key():
    with pytest.raises((TypeError, ValidationError)):
        Measurement(key="recommended_refund", value=1)


def test_measurement_rejects_verdict_shaped_value():
    with pytest.raises((TypeError, ValidationError)):
        Measurement(key="note", value="refund granted")


def test_evaluator_output_carries_no_verdict_route():
    policy = _policy()
    facts = {
        "ride": {"quoted_fare_cents": 1200, "charged_fare_cents": 1600},
        "route": {"planned_distance_km": 10.0, "actual_distance_km": 14.0,
                  "planned_duration_s": 1500, "actual_duration_s": 1800, "stops": []},
    }
    ctx = evaluator.evaluate("route_deviation", facts, policy)
    # It measured the deviation…
    assert ctx.measurement("deviation_pct") is not None
    assert ctx.measurement("deviation_pct").value == 40.0
    # …and it selected rule ids…
    assert "RP-ROUTE-003" in ctx.rule_ids()
    # …but nothing the policy layer COMPUTED is a verdict. Rule *text* legitimately quotes
    # policy vocabulary ("refund of the excess"); that is the prose the Judge reasons over,
    # not a per-case verdict. So we check field NAMES and computed measurement VALUES only.
    _assert_no_computed_verdict(ctx)


def _assert_no_computed_verdict(ctx) -> None:
    # No field name anywhere in the context (or nested rules/measurements) is verdict-shaped.
    for name in type(ctx).model_fields:
        assert not VERDICT_RE.search(name)
    for rule in ctx.applicable_rules:
        for name in type(rule).model_fields:
            assert not VERDICT_RE.search(name)
    # No measurement KEY or computed VALUE is verdict-shaped.
    for meas in ctx.measurements:
        assert not VERDICT_RE.search(meas.key), f"measurement key {meas.key} is verdict-shaped"
        if isinstance(meas.value, str):
            assert not VERDICT_RE.search(meas.value), f"measurement value {meas.value!r} verdict-shaped"
    # The measurement map — the only per-case computed payload — has no verdict token in it.
    map_blob = str(ctx.measurement_map()).lower()
    for token in ("ruling", "verdict", "recommend", "no_action", "compensation"):
        assert token not in map_blob


def test_evaluator_output_carries_no_verdict_noshow():
    policy = _policy()
    facts = {
        "ride": {"charged_fare_cents": 500, "driver_waited_seconds": 120},
        "gps": {"min_distance_to_pickup_m": 300.0},
        "chat": {"messages": []},
        "fare": {"cancellation_fee_cents": 500},
    }
    ctx = evaluator.evaluate("no_show", facts, policy)
    assert ctx.measurement("driver_reached_pickup").value is False
    _assert_no_computed_verdict(ctx)
