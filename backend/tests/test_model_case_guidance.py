"""Regression checks for model instructions derived from the diagnostic review audit."""

from app.models.components import _advocate_focus, _judge_decision_checks


def test_route_judge_guidance_requires_fare_reconciliation_not_distance_inference():
    checks = " ".join(_judge_decision_checks("route_deviation")).lower()
    assert "quoted fare" in checks
    assert "itemised receipt/payment" in checks
    assert "longer or different route alone does not establish a refund" in checks
    assert "unexplained charge difference" in checks


def test_cancellation_judge_guidance_separates_charge_types_and_voucher_amounts():
    checks = " ".join(_judge_decision_checks("other_cancellation_fee"))
    assert "rider cancellation charge, rider waiting charge, or driver payout" in checks
    assert "S$6.61 cancellation or S$5 waiting" in checks
    assert "A driver payout is not a rider refund" in checks
    assert "30 days" in checks


def test_advocate_guidance_is_party_specific_but_requires_fair_acknowledgement():
    rider = " ".join(_advocate_focus("rider", "route_deviation"))
    driver = " ".join(_advocate_focus("driver", "route_deviation"))
    assert "rider's claim" in rider
    assert "driver's response" in driver
    assert "acknowledge the strongest contrary fact" in rider
    assert "acknowledge the strongest contrary fact" in driver
    assert "route length alone does not prove a refund" in rider


def test_fare_judge_guidance_abstains_on_unreconciled_difference():
    checks = " ".join(_judge_decision_checks("fare_calculation")).lower()
    assert "itemised components" in checks
    assert "receipt and charged payment" in checks
    assert "unreconciled difference does not authorize an invented refund amount" in checks
