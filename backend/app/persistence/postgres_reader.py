"""Postgres reader adapter — the integration seam.

Depends on the database specialist's reader package (`database.reader`, a path dependency) and
does NOT reimplement its SQL (docs/00-ownership.md §3). It calls the eight accessors and
translates their Pydantic models into the backend's own record shapes
(`app.persistence.reader`). The database accessors read their connection from `DATABASE_URL`
in the environment and RAISE `LookupError` on a missing row; this adapter maps a missing row to
`None` (the backend Protocol's contract) and any connection/operational error to
`DatabaseUnavailable`, so a downed database yields `database_unavailable` and never a ruling.

Connection: the read-only role `ryde_backend_readonly` (SELECT only on `ride_data` /
`case_archive`). The backend's own `tribunal` schema is written through a SEPARATE, writable
connection — two connections, two privilege levels (ASSUMPTIONS A-11).
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from app.persistence.reader import (
    ArchiveCase,
    ChatLog,
    ChatMessage,
    DatabaseUnavailable,
    FareBreakdown,
    FareComponent,
    GpsSample,
    GpsSamples,
    Profile,
    RideRecord,
    RouteRecord,
    assert_archive_id,
)

# Depend on the database specialist's reader package WITHOUT reimplementing its SQL
# (docs/00-ownership.md §3). Its `pyproject.toml` declares no build-backend package layout, so
# uv/pip cannot build it as a wheel and I must not edit its tree; instead the repo-root is put
# on sys.path so `database.reader` imports directly. This is a runtime path dependency — the
# accessors and their SQL still live entirely in `database/`.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from database.reader import (  # type: ignore  # noqa: E402
    get_archive_case as db_get_archive_case,
    get_chat_log as db_get_chat_log,
    get_fare_breakdown as db_get_fare_breakdown,
    get_gps_samples as db_get_gps_samples,
    get_profile as db_get_profile,
    get_ride as db_get_ride,
    get_route as db_get_route,
    search_archive as db_search_archive,
)


def _iso(dt) -> str:
    return dt.isoformat().replace("+00:00", "Z") if dt is not None else ""


def _f(v) -> float:
    return float(v) if isinstance(v, Decimal) else (v if v is not None else 0.0)


class PostgresReader:
    """Read-only adapter over the database package's accessors.

    `read_dsn` is a PLAIN psycopg DSN (postgresql://ryde_backend_readonly@host:5432/
    ryde_tribunal), NOT a SQLAlchemy URL — the accessors connect with psycopg directly.
    """

    def __init__(self, read_dsn: str) -> None:
        self._dsn = read_dsn

    @contextmanager
    def _accessor_env(self):
        prev = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self._dsn
        try:
            yield
        finally:
            if prev is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = prev

    def _call(self, fn, *args):
        """Run a database accessor; map missing-row -> None, connection error -> DatabaseUnavailable."""
        with self._accessor_env():
            try:
                return fn(*args)
            except LookupError:
                return None
            except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
                raise DatabaseUnavailable(str(exc)) from exc

    # --- accessors -----------------------------------------------------------
    def get_ride(self, ride_id: str) -> RideRecord | None:
        r = self._call(db_get_ride, ride_id)
        if r is None:
            return None
        route = self._call(db_get_route, ride_id)
        waited = route.driver_wait_seconds if route is not None else None
        return RideRecord(
            ride_id=r.ride_id,
            rider_id=r.rider_user_id,
            driver_id=r.driver_user_id,
            booked_at=_iso(r.requested_at),
            completed_at=_iso(r.dropoff_at) if r.dropoff_at else None,
            status=r.ride_status,
            quoted_fare_cents=r.quoted_fare.amount_cents,
            charged_fare_cents=r.fare_total.amount_cents,
            currency=r.quoted_fare.currency,
            planned_distance_km=r.quoted_distance_meters / 1000.0,
            estimated_duration_s=r.quoted_duration_seconds,
            driver_waited_seconds=waited,
        )

    def get_route(self, ride_id: str) -> RouteRecord | None:
        r = self._call(db_get_route, ride_id)
        if r is None:
            return None
        stops = [
            {
                "duration_s": s.duration_seconds,
                "rider_requested": s.rider_requested,
                "started_at": _iso(s.started_at),
                "ended_at": _iso(s.ended_at),
            }
            for s in r.stops
        ]
        return RouteRecord(
            ride_id=r.ride_id,
            planned_distance_km=r.planned_distance_meters / 1000.0,
            actual_distance_km=r.actual_distance_meters / 1000.0,
            planned_duration_s=r.planned_duration_seconds,
            actual_duration_s=r.actual_duration_seconds,
            stops=stops,
            rider_requested_change=any(s.rider_requested for s in r.stops),
            diversion_evidenced=False,  # no conditions-data field in the DB model
        )

    def get_gps_samples(self, ride_id: str) -> GpsSamples | None:
        samples = self._call(db_get_gps_samples, ride_id)
        if samples is None:
            return None
        route = self._call(db_get_route, ride_id)
        min_d = route.driver_arrival_distance_meters if route is not None else None
        out = [
            GpsSample(seq=s.sample_id, lat=_f(s.lat), lon=_f(s.lon),
                      at=_iso(s.sample_at), accuracy_m=_f(s.accuracy_meters))
            for s in samples
        ]
        return GpsSamples(
            ride_id=ride_id,
            samples=out,
            min_distance_to_pickup_m=float(min_d) if min_d is not None else None,
        )

    def get_chat_log(self, ride_id: str) -> ChatLog | None:
        msgs = self._call(db_get_chat_log, ride_id)
        if msgs is None:
            return None
        out = [
            ChatMessage(seq=i + 1, role=m.participant_role, at=_iso(m.sent_at),
                        text=m.message_text, kind="message")
            for i, m in enumerate(msgs)
        ]
        return ChatLog(ride_id=ride_id, messages=out)

    def get_fare_breakdown(self, ride_id: str) -> FareBreakdown | None:
        f = self._call(db_get_fare_breakdown, ride_id)
        if f is None:
            return None
        components = [
            FareComponent(name="base", amount_cents=f.base_fare.amount_cents),
            FareComponent(name="distance", amount_cents=f.distance_fare.amount_cents),
            FareComponent(name="time", amount_cents=f.time_fare.amount_cents),
            FareComponent(name="waiting", amount_cents=f.waiting_fare.amount_cents),
            FareComponent(name="surge", amount_cents=f.surge_fare.amount_cents),
        ]
        return FareBreakdown(
            ride_id=ride_id,
            currency=f.total_fare.currency,
            components=components,
            surge_multiplier=_f(f.surge_multiplier),
            cancellation_fee_cents=f.cancellation_fee.amount_cents,
            promo_code=(f.promos[0].promo_code if f.promos else None),
            promo_applied=bool(f.promos),
            adjustments=[FareComponent(name=a.adjustment_type, amount_cents=a.amount.amount_cents)
                         for a in f.adjustments],
        )

    def get_profile(self, user_id: str) -> Profile | None:
        p = self._call(db_get_profile, user_id)
        if p is None:
            return None
        return Profile(
            user_id=p.user_id,
            account_age_days=p.account_age_days,
            avg_rating=_f(p.average_rating),
            disputes_total=p.dispute_counts.disputes_180d,
            disputes_last_30d=p.dispute_counts.disputes_30d,
            prior_classifications=list(p.prior_classifications),
        )

    def search_archive(
        self, category: str, features: dict[str, Any], limit: int
    ) -> list[ArchiveCase]:
        results = self._call(db_search_archive, category, features, limit)
        if results is None:
            return []
        return [
            ArchiveCase(
                archive_case_id=a.archive_case_id,
                category=a.category,
                ruling_type=a.decision.ruling_type,
                recommended_action=a.decision.recommended_action_description,
                confidence=_f(a.decision.confidence) if a.decision.confidence is not None else 0.0,
                decision_origin=a.decision.decision_origin,
                policy_version=a.policy_version,
                features=dict(a.feature_vector),
            )
            for a in results
        ]

    def get_archive_case(self, archive_case_id: str) -> ArchiveCase | None:
        assert_archive_id(archive_case_id)  # I-2a: reject a live id before touching the DB
        a = self._call(db_get_archive_case, archive_case_id)
        if a is None:
            return None
        return ArchiveCase(
            archive_case_id=a.archive_case_id,
            category=a.category,
            ruling_type=a.decision.ruling_type,
            recommended_action=a.decision.recommended_action_description,
            confidence=_f(a.decision.confidence) if a.decision.confidence is not None else 0.0,
            decision_origin=a.decision.decision_origin,
            policy_version=a.policy_version,
            was_overridden=a.human_review.human_reviewed,
        )
