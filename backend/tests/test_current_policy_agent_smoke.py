from pathlib import Path

import pytest

from tests.current_policy_agent_smoke import CASES, ROOT, run


def test_current_policy_smoke_uses_synthetic_cases_and_keeps_labels_out_of_filings():
    assert len(CASES) == 9
    assert {case["category"] for case in CASES} == {
        "route_deviation", "fare_calculation", "no_show_charge", "other_cancellation_fee",
    }
    assert len({case["key"] for case in CASES}) == len(CASES)
    assert all("expected_" not in key for case in CASES for key in case if key not in {
        "expected_status", "expected_ruling", "expected_amount"
    })


def test_offline_smoke_confirms_clear_and_hard_stop_paths_without_provider_calls(tmp_path):
    result = run(tmp_path / "current-policy-smoke", live=False, env_file=None,
                 model="not-used-offline")

    assert result["policy_version"] == "ryde-policy-1.1.0"
    assert result["database_connected"] is False
    assert result["expected_labels_sent_to_app"] is False
    assert result["outcome_accuracy"] == 1.0
    assert result["judge_provider_calls"] == 0
    assert result["non_judge_provider_calls"] == 0
    assert result["fallback_count"] == 0
    assert all(not row["validator_errors"] for row in result["rows"]
               if row["expected_status"] == "resolved")
    assert result["provider_reported_usage"] is None


def test_smoke_refuses_to_write_populated_outputs_inside_repository(tmp_path):
    target = ROOT / "backend/tests/not-a-real-output"
    with pytest.raises(ValueError, match="outside the repository"):
        run(target, live=False, env_file=None, model="unused")
