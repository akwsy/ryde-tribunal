"""Date-scoped reviewer dashboard endpoints."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from app.api.container import Container
from app.api.metrics_helpers import (
    METRIC_TZ,
    METRIC_ZONE,
    _dimension_key,
    _in_range,
    _slice_label,
    _timeseries_points,
)

_METRIC_DIMENSIONS = {"category", "status", "filed_by", "provider"}


def register_metrics_routes(
    app: FastAPI,
    container: Container,
    store,
    reader,
    error_response: Callable[..., JSONResponse],
    filed_rows: Callable[..., Any],
    is_human_review: Callable[..., bool],
) -> None:
    """Register the dashboard metric routes against the shared app dependencies."""
    def _metric_bounds(
        from_date: date | None, to_date: date | None, tz: str
    ) -> tuple[tuple[datetime, datetime] | None, JSONResponse | None]:
        if from_date is None or to_date is None:
            return None, error_response("validation_error", "from and to dates are required", 422)
        if tz != METRIC_TZ:
            return None, error_response("validation_error", "tz must be Asia/Singapore", 422)
        if to_date < from_date:
            return None, error_response("validation_error", "to must be on or after from", 422)
        start = datetime.combine(from_date, time.min, METRIC_ZONE).astimezone(timezone.utc)
        end = datetime.combine(to_date + timedelta(days=1), time.min, METRIC_ZONE).astimezone(timezone.utc)
        return (start, end), None

    @app.get("/api/v1/metrics/overview")
    def metrics_overview(
        from_: date | None = Query(default=None, alias="from"),
        to: date | None = None,
        tz: str = METRIC_TZ,
    ):
        bounds, error = _metric_bounds(from_, to, tz)
        if error:
            return error
        start, end = bounds
        rows, error = filed_rows(store, reader, container.settings.escalation_confidence_threshold)
        if error:
            return error
        in_range = [row for row in rows if _in_range(row["case"].filed_at, start, end)]
        resolved = sum(
            1 for row in in_range
            if row["result"] and row["result"].get("status") == "resolved"
            and not (row["result"].get("judge") or {}).get("escalation", {}).get("escalated", False)
            and not row["result"].get("_archive_needs_review", False)
        )
        pending = sum(1 for row in in_range if is_human_review(row["case"], row["result"]))
        return {
            "from": from_.isoformat(), "to": to.isoformat(), "timezone": tz,
            "filed": len(in_range), "auto_resolved": resolved,
            "human_intervention": pending,
        }

    @app.get("/api/v1/metrics/timeseries")
    def metrics_timeseries(
        from_: date | None = Query(default=None, alias="from"),
        to: date | None = None,
        tz: str = METRIC_TZ,
        group_by: str = "category",
    ):
        bounds, error = _metric_bounds(from_, to, tz)
        if error:
            return error
        if group_by not in _METRIC_DIMENSIONS:
            return error_response("validation_error", "unsupported group_by dimension", 422)
        start, end = bounds
        rows, error = filed_rows(store, reader, container.settings.escalation_confidence_threshold)
        if error:
            return error
        selector = getattr(app.state, "metrics_bucket_selector", None)
        if selector is None:
            return error_response("internal_error", "time-series bucket thresholds are not configured", 503)
        range_days = (
            end.astimezone(METRIC_ZONE).date()
            - start.astimezone(METRIC_ZONE).date()
        ).days
        granularity = selector(range_days)
        if granularity not in {"day", "week", "month", "year"}:
            return error_response("internal_error", "configured bucket selector returned an invalid bucket", 500)
        points = _timeseries_points(rows, start, end, group_by, granularity)
        return {"timezone": tz, "granularity": granularity, "group_by": group_by,
                "points": points}

    @app.get("/api/v1/metrics/breakdown")
    def metrics_breakdown(
        from_: date | None = Query(default=None, alias="from"),
        to: date | None = None,
        tz: str = METRIC_TZ,
        by: str = "category",
    ):
        bounds, error = _metric_bounds(from_, to, tz)
        if error:
            return error
        if by not in _METRIC_DIMENSIONS:
            return error_response("validation_error", "unsupported breakdown dimension", 422)
        start, end = bounds
        rows, error = filed_rows(store, reader, container.settings.escalation_confidence_threshold)
        if error:
            return error
        counts: dict[str, int] = {}
        for row in rows:
            if _in_range(row["case"].filed_at, start, end):
                key = _dimension_key(row["case"], row["result"], by)
                counts[key] = counts.get(key, 0) + 1
        return {
            "timezone": tz, "by": by,
            "slices": [{"key": key, "label": _slice_label(key), "count": count}
                       for key, count in sorted(counts.items())],
        }

    @app.get("/api/v1/metrics/ai-usage")
    def metrics_ai_usage(
        from_: date | None = Query(default=None, alias="from"),
        to: date | None = None,
        tz: str = METRIC_TZ,
    ):
        bounds, error = _metric_bounds(from_, to, tz)
        if error:
            return error
        start, end = bounds
        rows, error = filed_rows(store, reader, container.settings.escalation_confidence_threshold)
        if error:
            return error
        in_range = [row for row in rows if _in_range(row["case"].filed_at, start, end)
                    and row.get("result")]
        category_counts: dict[str, dict[str, int]] = {}
        skip_reason_counts: dict[str, int] = {}
        policy_resolved = 0
        evidence_resolved = 0
        human_only_cases = 0
        invoked = 0
        for row in in_range:
            result = row["result"]
            trace = result.get("trace", [])
            called = any(item.get("event") == "gemini_escalation" for item in trace)
            skipped = [item for item in trace
                       if item.get("event") == "human_review_without_model"]
            invoked += int(called)
            category = row["case"].category
            counts = category_counts.setdefault(category, {
                "adjudicated_cases": 0, "gemini_review_cases": 0,
                "human_review_without_model_cases": 0,
            })
            counts["adjudicated_cases"] += 1
            counts["gemini_review_cases"] += int(called)
            if skipped:
                human_only_cases += 1
                counts["human_review_without_model_cases"] += 1
                for item in skipped:
                    for code in item.get("reason_codes", []) or ["uncategorized"]:
                        skip_reason_counts[code] = skip_reason_counts.get(code, 0) + 1
            if result.get("status") == "resolved":
                if any(item.get("event") == "rules_first_review" for item in trace):
                    policy_resolved += 1
                if any(item.get("event") == "repair_satisfied" for item in trace):
                    evidence_resolved += 1
        total = len(in_range)
        share = round(invoked / total, 4) if total else None
        by_category = []
        for category, counts in sorted(category_counts.items()):
            amount = counts["adjudicated_cases"]
            by_category.append({**counts, "category": category,
                                "gemini_review_share": round(counts["gemini_review_cases"] / amount, 4)
                                if amount else None})
        return {
            "from": from_.isoformat(), "to": to.isoformat(), "timezone": tz,
            "adjudicated_cases": total, "gemini_review_cases": invoked,
            "gemini_review_share": share, "target_share": 0.25,
            "target_gap": round(share - 0.25, 4) if share is not None else None,
            "human_review_without_model_cases": human_only_cases,
            "human_review_without_model_reasons": [
                {"reason_code": code, "count": count}
                for code, count in sorted(skip_reason_counts.items())
            ],
            "resolved_by_policy_rules": policy_resolved,
            "resolved_after_evidence_check": evidence_resolved,
            "by_category": by_category,
        }
