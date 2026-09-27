"""Pure helpers for date-scoped dashboard metrics."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.persistence.reader import CaseRecord

METRIC_TZ = "Asia/Singapore"
METRIC_ZONE = ZoneInfo(METRIC_TZ)


def _parse_datetime(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _in_range(value: str | datetime, start: datetime, end: datetime) -> bool:
    filed = _parse_datetime(value)
    return start <= filed < end


def _dimension_key(
    case: CaseRecord, result: dict[str, Any] | None, dimension: str
) -> str:
    result = result or {}
    if dimension == "category":
        return case.category or "unknown"
    if dimension == "filed_by":
        return case.filed_by or "unknown"
    if dimension == "status":
        return result.get("status") or "queued"
    provider = ((result.get("judge") or {}).get("provider") or {})
    if provider.get("kind") == "deterministic-mock":
        return "local deterministic"
    return provider.get("display_name") or "unknown"


def _slice_label(key: str) -> str:
    labels = {
        "route_deviation": "Route deviation",
        "no_show_charge": "No-show charge",
        "fare_calculation": "Fare calculation",
        "other_cancellation_fee": "Other cancellation fee",
        "property_damage": "Property damage",
        "safety_incident": "Safety incident",
        "lost_item": "Lost item",
        "conduct_complaint": "Conduct complaint",
        "local deterministic": "Local deterministic",
        "unknown": "Unknown",
        "queued": "Queued",
        "resolved": "Resolved",
        "escalated": "Escalated",
        "pending_review": "Pending review",
        "overridden": "Overridden",
        "rider": "Rider",
        "driver": "Driver",
    }
    return labels.get(key, key)


def _bucket_start(day: date, granularity: str) -> date:
    if granularity == "day":
        return day
    if granularity == "week":
        return day - timedelta(days=(day.weekday() + 1) % 7)
    if granularity == "month":
        return day.replace(day=1)
    if granularity == "year":
        return day.replace(month=1, day=1)
    raise ValueError(f"unsupported granularity {granularity!r}")


def _timeseries_points(
    rows: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    group_by: str,
    granularity: str,
) -> list[dict[str, Any]]:
    counts: dict[date, dict[str, int]] = {}
    for row in rows:
        case = row["case"]
        filed = _parse_datetime(case.filed_at).astimezone(METRIC_ZONE).date()
        if not (start.astimezone(METRIC_ZONE).date() <= filed < end.astimezone(METRIC_ZONE).date()):
            continue
        bucket = _bucket_start(filed, granularity)
        key = _dimension_key(case, row["result"], group_by) or "unknown"
        series = counts.setdefault(bucket, {})
        series[key] = series.get(key, 0) + 1
    return [
        {"date": bucket.isoformat(), "series": [
            {"key": key, "count": value} for key, value in sorted(series.items())
        ]}
        for bucket, series in sorted(counts.items())
    ]
