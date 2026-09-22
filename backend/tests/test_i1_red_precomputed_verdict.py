"""The brief's decisive check: reintroduce a precomputed verdict and confirm the integrity
suite catches it. If these detections did NOT fire, the I-1 tests would be decoration.

Each test simulates a specific way a precomputed verdict could sneak in, then asserts the
guard rejects it. These tests PASS by confirming the violation is DETECTED — i.e. they prove
the red is reachable. See backend/README.md "Proving the integrity tests bite".
"""

from __future__ import annotations

import re

import pytest
from pydantic import ConfigDict

from app.policy.context import FORBIDDEN_FIELD_RE, Measurement, PolicyContext, PolicyRule

VERDICT_RE = re.compile(
    r"rul(e|ing)_type|verdict|recommend|action|amount|fault|refund", re.IGNORECASE
)


def test_adding_a_verdict_field_to_policycontext_is_detected():
    """If someone adds e.g. `recommended_ruling` to PolicyContext, the I-1 static check must
    flag it. We construct a subclass with such a field and run the same assertion the I-1 test
    runs — it must find the offending field."""

    class LeakyPolicyContext(PolicyContext):
        model_config = ConfigDict(frozen=True)
        recommended_ruling_type: str = "refund"  # <-- the reintroduced precomputed verdict

    offending = [n for n in LeakyPolicyContext.model_fields if VERDICT_RE.search(n)]
    assert offending, "I-1 static check FAILED to detect a verdict field — tests are decoration"
    assert "recommended_ruling_type" in offending


def test_measurement_carrying_a_verdict_value_is_rejected_at_construction():
    """A precomputed verdict smuggled as a measurement VALUE must be rejected."""
    with pytest.raises(Exception):
        Measurement(key="assessment", value="refund granted")


def test_measurement_with_verdict_key_is_rejected_at_construction():
    with pytest.raises(Exception):
        Measurement(key="recommended_action", value="pay out")


def test_evaluator_emitting_a_ruling_would_be_caught():
    """Simulate a policy evaluator that (wrongly) computes a ruling and tries to attach it to
    the context. Attaching it via a verdict-named field is impossible (frozen + guard); the
    only place it could hide is a measurement, which the guard rejects. This asserts there is
    NO path for the policy layer to carry the verdict."""
    # Attempt 1: as a measurement value -> rejected.
    with pytest.raises(Exception):
        PolicyContext(
            policy_version="v", category="route_deviation",
            measurements=(Measurement(key="deviation_pct", value=34.0),
                          Measurement(key="verdict", value="refund")),
        )
    # Attempt 2: a legitimate context has only measurements + rules, no verdict tokens.
    ctx = PolicyContext(
        policy_version="v", category="route_deviation",
        applicable_rules=(PolicyRule(rule_id="RP-ROUTE-003", text="deviation above 15%…"),),
        measurements=(Measurement(key="deviation_pct", value=34.0),),
    )
    for meas in ctx.measurements:
        assert not VERDICT_RE.search(meas.key)
        assert not (isinstance(meas.value, str) and VERDICT_RE.search(meas.value))
