import importlib.util
from collections import Counter
from pathlib import Path


def _module():
    path = Path(__file__).with_name("selective_routing_benchmark.py")
    spec = importlib.util.spec_from_file_location("selective_routing_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_routing_set_is_balanced_and_keeps_expected_labels_out_of_records():
    module = _module()
    cases = module.cases()
    assert len(cases) == 120
    assert len({case["scenario_family"] for case in cases}) == 120
    assert Counter(case["routing_group"] for case in cases) == {
        "rules_clear": 30, "verified_evidence": 30,
        "model_eligible": 30, "human_hard_stop": 30,
    }
    assert Counter(case["category"] for case in cases) == {
        "route_deviation": 45, "no_show_charge": 75,
    }
    assert sum(case["expected_route"] == "gemini" for case in cases) == 30
    assert all(case["expected_outcome"]["status"] == "escalated"
               for case in cases if case["expected_route"] == "gemini")
    assert len({(case.get("planned_km"), case.get("actual_km"),
                 case.get("quoted_cents"), case.get("charged_cents"))
                for case in cases if case["category"] == "route_deviation"}) >= 40

    reader = module._BASE.BenchmarkReader(cases[0])
    for record in (reader.ride, reader.route, reader.fare):
        assert record is None or not any(
            key in {"expected_route", "expected_outcome", "routing_group"}
            for key in record.model_dump()
        )
    assert reader.search_archive() == []


def test_selective_routing_case_selection_is_stable_and_rejects_unknown_keys():
    module = _module()
    selected = module.select_cases(["hardstop-03", "interpret-01"])
    assert [case["key"] for case in selected] == ["hardstop-03", "interpret-01"]
    assert [case["expected_route"] for case in selected] == ["human", "gemini"]
    try:
        module.select_cases(["missing-case"])
    except ValueError as exc:
        assert "missing-case" in str(exc)
    else:
        raise AssertionError("Unknown routing cases must be rejected")


def test_policy_version_can_be_overridden_without_changing_frozen_default():
    module = _module()
    import inspect

    assert inspect.signature(module.run).parameters["policy_version"].default == "ryde-policy-1.0.0"
