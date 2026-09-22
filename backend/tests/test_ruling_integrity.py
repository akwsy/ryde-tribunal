"""Ruling integrity — a refund/compensation MUST carry a positive amount (point 1).

`finalize_ruling` downgrades a figureless monetary remedy to no_action; `assert_ruling_integrity`
raises on one. A remedy without a figure can never be returned.
"""

from __future__ import annotations

import pytest

from app.orchestration.escalation import (
    RulingIntegrityError,
    assert_ruling_integrity,
    finalize_ruling,
)


def test_refund_with_null_amount_is_downgraded():
    ruling = {"ruling_type": "refund",
              "recommended_action": {"description": "refund the fee"}}  # no amount
    out, downgraded = finalize_ruling(ruling)
    assert downgraded is True
    assert out["ruling_type"] == "no_action"
    assert "amount" not in out["recommended_action"]


def test_refund_with_zero_amount_is_downgraded():
    ruling = {"ruling_type": "refund",
              "recommended_action": {"description": "refund",
                                     "amount": {"amount_cents": 0, "currency": "SGD"}}}
    out, downgraded = finalize_ruling(ruling)
    assert downgraded is True
    assert out["ruling_type"] == "no_action"


def test_refund_with_positive_amount_is_kept():
    ruling = {"ruling_type": "refund",
              "recommended_action": {"description": "refund",
                                     "amount": {"amount_cents": 500, "currency": "SGD"}}}
    out, downgraded = finalize_ruling(ruling)
    assert downgraded is False
    assert out["ruling_type"] == "refund"
    assert out["recommended_action"]["amount"]["amount_cents"] == 500


def test_no_action_needs_no_amount():
    ruling = {"ruling_type": "no_action", "recommended_action": {"description": "charge stands"}}
    out, downgraded = finalize_ruling(ruling)
    assert downgraded is False
    assert out["ruling_type"] == "no_action"


def test_assert_ruling_integrity_raises_on_figureless_refund():
    with pytest.raises(RulingIntegrityError):
        assert_ruling_integrity({"ruling_type": "refund",
                                 "recommended_action": {"description": "refund"}})
    with pytest.raises(RulingIntegrityError):
        assert_ruling_integrity({"ruling_type": "compensation",
                                 "recommended_action": {"amount": {"amount_cents": 0, "currency": "SGD"}}})


def test_assert_ruling_integrity_passes_valid():
    assert_ruling_integrity({"ruling_type": "refund",
                             "recommended_action": {"amount": {"amount_cents": 325, "currency": "SGD"}}})
    assert_ruling_integrity({"ruling_type": "no_action", "recommended_action": {}})
