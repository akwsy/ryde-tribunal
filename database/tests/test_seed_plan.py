from __future__ import annotations

from datetime import UTC, datetime

from seed.generator import (
    ADDITIONAL_ARCHIVE_CASE_COUNT,
    ADDITIONAL_RIDE_COUNT,
    ADDITIONAL_USER_COUNT,
    BASE_ARCHIVE_CASE_COUNT,
    BASE_RIDE_COUNT,
    CATEGORY_TAGS,
    _archive_case_times,
    _dt_for_ride,
    _rng,
)


def test_seed_plan_adds_the_requested_exact_record_counts():
    assert ADDITIONAL_USER_COUNT == 20
    assert ADDITIONAL_RIDE_COUNT == 100
    assert ADDITIONAL_ARCHIVE_CASE_COUNT == 15
    assert len(CATEGORY_TAGS) == 8


def test_original_ride_dates_remain_unchanged_and_added_dates_are_inclusive():
    rng = _rng("ride-data-v1:case-archive-v1")
    for _ in range(80):
        rng.randrange(0, 95)
    old_dates = [_dt_for_ride(rng, i) for i in range(1, BASE_RIDE_COUNT + 1)]
    assert min(old_dates) == datetime(2026, 7, 16, 7, 3, tzinfo=UTC)
    assert max(old_dates) == datetime(2026, 9, 13, 7, 52, tzinfo=UTC)

    added_dates = [_dt_for_ride(rng, i) for i in range(BASE_RIDE_COUNT + 1, BASE_RIDE_COUNT + ADDITIONAL_RIDE_COUNT + 1)]
    assert min(item.date() for item in added_dates).isoformat() >= "2026-06-01"
    assert max(item.date() for item in added_dates).isoformat() <= "2026-08-31"


def test_original_archive_filing_dates_remain_and_added_cases_file_after_trips():
    first_trip, first_filing = _archive_case_times(1)
    last_original_trip, last_original_filing = _archive_case_times(BASE_ARCHIVE_CASE_COUNT)
    assert first_filing == datetime(2025, 4, 16, tzinfo=UTC)
    assert last_original_filing == datetime(2026, 8, 25, tzinfo=UTC)
    assert first_trip < first_filing and last_original_trip < last_original_filing

    additions = [
        _archive_case_times(i)
        for i in range(BASE_ARCHIVE_CASE_COUNT + 1, BASE_ARCHIVE_CASE_COUNT + ADDITIONAL_ARCHIVE_CASE_COUNT + 1)
    ]
    for trip_at, filed_at in additions:
        assert datetime(2026, 6, 1, tzinfo=UTC) <= trip_at <= datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
        assert datetime(2026, 6, 1, tzinfo=UTC) <= filed_at <= datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
        assert filed_at > trip_at
    assert {CATEGORY_TAGS[(i - 1) % len(CATEGORY_TAGS)] for i in range(33, 48)} == set(CATEGORY_TAGS)
