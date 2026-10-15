import importlib.util
from pathlib import Path
from collections import Counter


def test_independent_benchmark_balance_and_no_expectations_in_live_records():
    spec=importlib.util.spec_from_file_location('benchmark',Path(__file__).with_name('submission_benchmark.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cases=module.cases()
    assert len(cases)==120
    assert sum(c['key'].startswith('route-') for c in cases)==50
    assert sum(c['key'].startswith('no-show-') for c in cases)==50
    assert sum(c['key'].startswith('review-') for c in cases)==20
    assert len({c['scenario_family'] for c in cases})==120
    assert len({(c.get('planned_km'),c.get('actual_km'),c.get('quoted_cents'),c.get('charged_cents'))
                for c in cases if c['category']=='route_deviation'}) >= 40
    assert len({c.get('elapsed') for c in cases if c['category']=='no_show_charge'}) >= 15
    reader=module.BenchmarkReader(cases[0])
    assert not any(k.startswith('expected') for k in reader.ride.model_dump())
    assert reader.search_archive()==[]
    assert not any('expected' in record.model_dump() for record in
                   (reader.ride,reader.route,reader.fare) if record is not None)


def test_benchmark_can_select_synthetic_core_category_smoke_cases():
    spec=importlib.util.spec_from_file_location('benchmark',Path(__file__).with_name('submission_benchmark.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    selected=module.select_cases(['no-show-00','route-01'])
    assert [case['key'] for case in selected]==['route-01','no-show-00']
    assert {case['category'] for case in selected}=={'route_deviation','no_show_charge'}
    try:
        module.select_cases(['not-a-real-case'])
    except ValueError as error:
        assert 'not-a-real-case' in str(error)
    else:
        raise AssertionError('Unknown benchmark keys must be rejected')


def test_nearest_rank_latency_percentile_handles_small_smoke_runs():
    spec=importlib.util.spec_from_file_location('benchmark',Path(__file__).with_name('submission_benchmark.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.percentile_nearest_rank([30.0,41.2],.95)==41.2
    assert module.percentile_nearest_rank([], .95) is None


def test_provider_usage_is_summed_only_from_returned_nonnegative_integer_counters():
    spec=importlib.util.spec_from_file_location('benchmark',Path(__file__).with_name('submission_benchmark.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.sum_usage([
        {'prompt_tokens':10,'completion_tokens':2},
        {'prompt_tokens':7,'completion_tokens':3},
    ])=={'prompt_tokens':17,'completion_tokens':5}
    assert module.sum_usage([{'token_label':'unknown','prompt_tokens':-1}]) is None
