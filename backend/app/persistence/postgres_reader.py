"""Postgres reader adapter — the integration seam.

Depends on the database specialist's reader package (`database.reader`, a path dependency) and
does NOT reimplement its SQL. It calls the eleven accessors and
translates their Pydantic models into the backend's own record shapes
(`app.persistence.reader`). The database accessors read their connection from `DATABASE_URL`
in the environment and RAISE `LookupError` on a missing row; this adapter maps a missing row to
`None` (the backend Protocol's contract) and any connection/operational error to
`DatabaseUnavailable`, so a downed database yields `database_unavailable` and never a ruling.

Connection: the read-only role `ryde_backend_readonly` (SELECT only on `ride_data` /
`case_archive`). The backend's own `tribunal` schema is written through a SEPARATE, writable
connection — two connections with separate privilege levels.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import psycopg

from app.persistence.reader import (
    ArchiveCase,
    ArchiveHistoryRecord,
    AppEvent,
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

# The repository root is an explicit PYTHONPATH dependency of this local monorepo service.
# The launcher and backend test configuration set it; direct invocations must set it too.
import database.reader as _db_reader

from database.reader import (
    get_archive_case as db_get_archive_case,
    list_archive_disputes as db_list_archive_disputes,
    get_chat_log as db_get_chat_log,
    get_fare_breakdown as db_get_fare_breakdown,
    get_app_events as db_get_app_events,
    get_gps_samples as db_get_gps_samples,
    get_profile as db_get_profile,
    get_ride as db_get_ride,
    get_route as db_get_route,
    search_archive as db_search_archive,
    search_rides as db_search_rides,
)


def _iso(dt) -> str:
    return dt.isoformat().replace("+00:00", "Z") if dt is not None else ""


def _f(v) -> float | None:
    return float(v) if isinstance(v, Decimal) else v


def _record_meta(record) -> dict[str, Any]:
    verified_at = getattr(record, "verified_at", None)
    return {
        "verification_status": getattr(record, "verification_status", None),
        "evidence_source": getattr(record, "evidence_source", None),
        "verified_by": getattr(record, "verified_by", None),
        "verified_at": _iso(verified_at) if verified_at else None,
        "provenance": dict(getattr(record, "provenance", None) or {}),
    }


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
            service_tier=r.service_tier,
            accepted_at=_iso(r.accepted_at) if r.accepted_at else None,
            pickup_at=_iso(r.pickup_at) if r.pickup_at else None,
            quoted_fare_cents=(r.quoted_fare.amount_cents if r.quoted_fare else None),
            charged_fare_cents=(r.fare_total.amount_cents if r.fare_total else None),
            currency=(r.quoted_fare.currency if r.quoted_fare else "SGD"),
            planned_distance_km=(r.quoted_distance_meters / 1000.0
                                 if r.quoted_distance_meters is not None else None),
            estimated_duration_s=r.quoted_duration_seconds,
            driver_waited_seconds=waited,
            synthetic=getattr(r, "synthetic", True),
            company_trip_id=getattr(r, "company_trip_id", None),
            source_system=getattr(r, "source_system", None),
            scheduled_at=(_iso(r.scheduled_at) if getattr(r, "scheduled_at", None) else None),
            cancellation_timestamp=(_iso(r.cancellation_at) if getattr(r, "cancellation_at", None)
                                    else None),
            cancellation_reason=getattr(r, "cancellation_reason", None),
            **_record_meta(r),
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
                "lat": _f(s.lat),
                "lon": _f(s.lon),
                "note": s.note,
            }
            for s in r.stops
        ]
        waypoints = [
            {"route_kind": w.route_kind, "sequence_no": w.sequence_no,
             "lat": _f(w.lat), "lon": _f(w.lon), "label": w.label,
             "recorded_at": _iso(w.recorded_at)}
            for w in r.waypoints
        ]
        return RouteRecord(
            ride_id=r.ride_id,
            pickup_label=r.pickup_label, pickup_lat=_f(r.pickup_lat), pickup_lon=_f(r.pickup_lon),
            dropoff_label=r.dropoff_label, dropoff_lat=_f(r.dropoff_lat), dropoff_lon=_f(r.dropoff_lon),
            planned_distance_km=(r.planned_distance_meters / 1000.0
                                 if r.planned_distance_meters is not None else None),
            actual_distance_km=(r.actual_distance_meters / 1000.0
                                if r.actual_distance_meters is not None else None),
            planned_duration_s=r.planned_duration_seconds,
            actual_duration_s=r.actual_duration_seconds,
            driver_arrival_distance_m=r.driver_arrival_distance_meters,
            driver_wait_seconds=r.driver_wait_seconds,
            driver_arrival_at=_iso(r.driver_arrival_at) if r.driver_arrival_at else None,
            driver_wait_start_at=_iso(r.driver_wait_start_at) if r.driver_wait_start_at else None,
            waypoints=waypoints,
            stops=stops,
            rider_requested_change=any(s.rider_requested for s in r.stops),
            diversion_evidenced=False,  # no conditions-data field in the DB model
            source_system=getattr(r, "source_system", None),
            **_record_meta(r),
        )

    def get_gps_samples(self, ride_id: str) -> GpsSamples | None:
        samples = self._call(db_get_gps_samples, ride_id)
        if samples is None:
            return None
        route = self._call(db_get_route, ride_id)
        min_d = route.driver_arrival_distance_meters if route is not None else None
        out = [
            GpsSample(seq=(s.sequence_no if getattr(s, "sequence_no", None) is not None else s.sample_id),
                      sequence_no=getattr(s, "sequence_no", None),
                      lat=_f(s.lat), lon=_f(s.lon), at=_iso(s.sample_at),
                      accuracy_m=_f(getattr(s, "accuracy_meters", None)),
                      accuracy_meters=_f(getattr(s, "accuracy_meters", None)),
                      sample_id=s.sample_id, status=getattr(s, "status", None),
                      speed_kmh=_f(getattr(s, "speed_kmh", None)),
                      speed_meters_per_second=_f(getattr(s, "speed_meters_per_second", None)),
                      collector=getattr(s, "collector", None),
                      source_system=getattr(s, "source_system", None), **_record_meta(s))
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
            ChatMessage(seq=(m.sequence_no if getattr(m, "sequence_no", None) is not None else i + 1),
                        role=m.participant_role,
                        at=_iso(m.sent_at), text=m.message_text,
                        kind=getattr(m, "message_type", "message"),
                        message_id=getattr(m, "message_id", None),
                        event_type=getattr(m, "message_type", None),
                        message_type=getattr(m, "message_type", "message"),
                        status=getattr(m, "status", None),
                        source_system=getattr(m, "source_system", None), **_record_meta(m))
            for i, m in enumerate(msgs)
        ]
        return ChatLog(ride_id=ride_id, messages=out)

    def get_app_events(self, ride_id: str) -> list[AppEvent]:
        events = self._call(db_get_app_events, ride_id) or []
        return [
            AppEvent(
                event_id=e.event_id,
                ride_id=e.ride_id,
                sequence_no=e.sequence_no,
                event_at=_iso(e.event_at),
                event_type=e.event_type,
                details=e.details,
                source_system=e.source_system,
                evidence_source=e.evidence_source,
                verification_status=e.verification_status,
                verified_by=e.verified_by,
                verified_at=_iso(e.verified_at) if e.verified_at else None,
                provenance=dict(e.provenance),
                synthetic=e.synthetic,
            )
            for e in events
        ]

    def get_fare_breakdown(self, ride_id: str) -> FareBreakdown | None:
        f = self._call(db_get_fare_breakdown, ride_id)
        if f is None:
            return None
        money_parts = [
            ("base", f.base_fare), ("distance", f.distance_fare),
            ("time", f.time_fare), ("waiting", f.waiting_fare), ("surge", f.surge_fare),
        ]
        components = [FareComponent(name=name, amount_cents=money.amount_cents)
                      for name, money in money_parts if money is not None]
        currency = next((money.currency for _, money in money_parts if money is not None), "SGD")
        return FareBreakdown(
            ride_id=ride_id,
            currency=currency,
            components=components,
            surge_multiplier=_f(f.surge_multiplier),
            waiting_fare_cents=f.waiting_fare.amount_cents if f.waiting_fare else None,
            cancellation_fee_cents=(f.cancellation_fee.amount_cents if f.cancellation_fee else None),
            promo_code=(f.promos[0].promo_code if f.promos else None),
            promo_applied=bool(f.promos) if f.promos else None,
            promo_expected_cents=(f.promos[0].amount.amount_cents if f.promos else None),
            platform_fee_cents=(f.platform_fee.amount_cents if f.platform_fee else None),
            total_fare_cents=(f.total_fare.amount_cents if f.total_fare else None),
            promos=[{"promo_code": p.promo_code, "amount_cents": p.amount.amount_cents,
                     "currency": p.amount.currency, "applied_at": _iso(p.applied_at)}
                    for p in f.promos],
            adjustments=[FareComponent(name=a.adjustment_type, amount_cents=a.amount.amount_cents)
                         for a in f.adjustments if a.amount is not None],
            source_system=getattr(f, "source_system", None),
            **_record_meta(f),
        )

    def get_profile(self, user_id: str) -> Profile | None:
        p = self._call(db_get_profile, user_id)
        if p is None:
            return None
        return Profile(
            user_id=p.user_id,
            account_age_days=p.account_age_days,
            avg_rating=_f(p.average_rating),
            role=p.role,
            display_handle=p.display_handle,
            created_at=_iso(p.created_at) if p.created_at else None,
            lifetime_completed_rides=p.lifetime_completed_rides,
            rating_trend=p.rating_trend,
            disputes_total=(p.dispute_counts.disputes_180d if p.dispute_counts else
                            (p.company_dispute_history.total if p.company_dispute_history else None)),
            disputes_last_30d=(p.dispute_counts.disputes_30d if p.dispute_counts else None),
            prior_classifications=list(p.prior_classifications or []),
            company_user_id=getattr(p, "company_user_id", None),
            source_system=getattr(p, "source_system", None),
            full_name=getattr(p, "full_name", None),
            total_trips=getattr(p, "total_trips", None),
            fraud_count=p.fraud_flag_count,
            fraud_details=p.fraud_flag_details,
            source_dispute_history=(p.company_dispute_history.model_dump()
                                    if p.company_dispute_history else None),
            payment_method=getattr(p, "payment_method", None),
            vehicle=getattr(p, "vehicle", None),
            **_record_meta(p),
        )

    def search_rides(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        results = self._call(db_search_rides, query, limit)
        return [result.model_dump(mode="json") for result in (results or [])]

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
                rulings=[
                    {
                        "stage": ruling.stage,
                        "ruling_type": ruling.decision.ruling_type,
                        "recommended_action": ruling.decision.recommended_action_description,
                        "confidence": _f(ruling.decision.confidence)
                        if ruling.decision.confidence is not None else 0.0,
                        "decision_origin": ruling.decision.decision_origin,
                        "decided_at": _iso(ruling.decision.decided_at),
                    }
                    for ruling in a.rulings
                ],
            )
            for a in results
        ]

    def get_archive_case(self, archive_case_id: str) -> ArchiveCase | None:
        # Canonical IDs do not encode source. This method invokes only the archive accessor.
        assert_archive_id(archive_case_id)
        a = self._call(db_get_archive_case, archive_case_id)
        if a is None:
            return None
        return ArchiveCase(
            archive_case_id=a.archive_case_id,
            archive_ride_id=getattr(a, "archive_ride_id", None),
            category=a.category,
            ruling_type=a.decision.ruling_type,
            recommended_action=a.decision.recommended_action_description,
            confidence=_f(a.decision.confidence) if a.decision.confidence is not None else 0.0,
            decision_origin=a.decision.decision_origin,
            policy_version=a.policy_version,
            was_overridden=a.human_review.human_reviewed,
            archive_record=(
                a.model_dump(mode="json") if callable(getattr(a, "model_dump", None)) else {}
            ),
            rulings=[
                {
                    "stage": ruling.stage,
                    "ruling_type": ruling.decision.ruling_type,
                    "recommended_action": ruling.decision.recommended_action_description,
                    "confidence": _f(ruling.decision.confidence)
                    if ruling.decision.confidence is not None else 0.0,
                    "decision_origin": ruling.decision.decision_origin,
                    "decided_at": _iso(ruling.decision.decided_at),
                }
                for ruling in a.rulings
            ],
        )

    def list_archive_disputes(
        self, limit: int | None = 200
    ) -> list[ArchiveHistoryRecord]:
        results = self._call(db_list_archive_disputes, limit)
        if results is None:
            return []
        return [
            ArchiveHistoryRecord(
                archive_case_id=case.archive_case_id,
                archive_ride_id=case.archive_ride_id,
                category=case.category,
                subject=case.subject,
                filed_by=case.filed_by,
                created_at=_iso(case.created_at),
                policy_version=case.policy_version,
                verdict=case.decision.verdict,
                ruling_type=case.decision.ruling_type,
                recommended_action=case.decision.recommended_action_description,
                amount_cents=case.decision.recommended_amount.amount_cents,
                currency=case.decision.recommended_amount.currency,
                confidence=_f(case.decision.confidence),
                decision_origin=case.decision.decision_origin,
                human_reviewed=case.human_reviewed,
                rulings=[
                    {
                        "stage": ruling.stage,
                        "verdict": ruling.decision.verdict,
                        "ruling_type": ruling.decision.ruling_type,
                        "recommended_action": ruling.decision.recommended_action_description,
                        "amount_cents": ruling.decision.recommended_amount.amount_cents,
                        "currency": ruling.decision.recommended_amount.currency,
                        "confidence": _f(ruling.decision.confidence),
                        "decision_origin": ruling.decision.decision_origin,
                        "decided_at": _iso(ruling.decision.decided_at),
                    }
                    for ruling in case.rulings
                ],
                synthetic=case.synthetic,
            )
            for case in results
        ]
