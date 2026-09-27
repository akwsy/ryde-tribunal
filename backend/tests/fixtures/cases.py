"""Synthetic case builders for tests. All data is fictional. Live records carry NO outcome
fields. Archive and live disputes share DSP-###### IDs, allocated distinctly in fixtures.

Each builder takes distinguishing numbers so a test can generate materially different cases —
the raw material for the I-5 case-specificity suite.
"""

from __future__ import annotations

from app.persistence.reader import (
    ArchiveCase,
    CaseRecord,
    ChatLog,
    ChatMessage,
    EvidenceRef,
    FareBreakdown,
    FareComponent,
    GpsSamples,
    Profile,
    RideRecord,
    RouteRecord,
)
from tests.fixtures.reader import FixtureReader


def _ev_base(ride_id: str) -> int:
    """Per-ride base for clean EV-\\d{6} fixture ids, in a high range (700000+) disjoint from
    the assembled-bundle range (derived from the ride number, far below)."""
    import re as _re
    digits = int(_re.sub(r"\D", "", ride_id) or "0") % 2000
    return 700000 + digits * 10


def _ev(
    evidence_id: str,
    class_: str,
    source: str,
    verification_status: str,
    payload: dict,
    visibility: str = "both",
    method: str = "",
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        class_=class_,
        source=source,
        visibility=visibility,
        verification_status=verification_status,
        verification_method=method,
        recorded_at="2026-09-22T06:40:00Z",
        provenance={"table": class_, "row_ids": [evidence_id]},
        payload=payload,
    )


def route_case(
    reader: FixtureReader,
    *,
    store=None,
    case_id: str,
    ride_id: str,
    planned_km: float,
    actual_km: float,
    quoted_cents: int,
    charged_cents: int,
    justified: bool = False,
    rider_disputes_30d: int = 0,
    stop_seconds: int = 0,
) -> CaseRecord:
    reader.rides[ride_id] = RideRecord(
        ride_id=ride_id, rider_id=f"USR-R-{ride_id[-6:]}", driver_id=f"USR-D-{ride_id[-6:]}",
        booked_at="2026-09-22T06:00:00Z", completed_at="2026-09-22T06:40:00Z",
        status="completed", quoted_fare_cents=quoted_cents, charged_fare_cents=charged_cents,
        planned_distance_km=planned_km, estimated_duration_s=1500,
    )
    reader.routes[ride_id] = RouteRecord(
        ride_id=ride_id, planned_distance_km=planned_km, actual_distance_km=actual_km,
        planned_duration_s=1500, actual_duration_s=1700,
        stops=([{"duration_s": stop_seconds, "rider_requested": False}] if stop_seconds else []),
        rider_requested_change=justified, diversion_evidenced=justified,
    )
    reader.gps[ride_id] = GpsSamples(ride_id=ride_id, samples=[], min_distance_to_pickup_m=5.0)
    reader.fares[ride_id] = FareBreakdown(
        ride_id=ride_id,
        components=[FareComponent(name="base", amount_cents=quoted_cents)],
        surge_multiplier=1.0, cancellation_fee_cents=0,
    )
    reader.profiles[reader.rides[ride_id].rider_id] = Profile(
        user_id=reader.rides[ride_id].rider_id, account_age_days=400, avg_rating=4.8,
        disputes_total=rider_disputes_30d, disputes_last_30d=rider_disputes_30d,
    )
    reader.profiles[reader.rides[ride_id].driver_id] = Profile(
        user_id=reader.rides[ride_id].driver_id, account_age_days=900, avg_rating=4.9,
    )
    _b = _ev_base(ride_id)
    ev = [
        _ev(f"EV-{_b + 1:06d}", "gps_telemetry", "system_record", "verified",
            {"actual_distance_km": actual_km, "_question": "distance"}, method="device_gps_signed"),
        _ev(f"EV-{_b + 2:06d}", "fare", "system_record", "verified",
            {"planned_distance_km": planned_km, "_question": "distance"}, method="fare_ledger"),
    ]
    case = CaseRecord(
        case_id=case_id, ride_id=ride_id, category="route_deviation", filed_by="rider",
        subject="Charged more than quoted", description="Route looked much longer than booked.",
        filed_at="2026-09-22T07:00:00Z", evidence=ev,
    )
    if store is not None:
        store.save_filed_case(case)
    return case


def noshow_case(
    reader: FixtureReader,
    *,
    store=None,
    case_id: str,
    ride_id: str,
    reached_pickup: bool,
    waited_seconds: int,
    contact_attempt: bool,
    fee_cents: int,
    min_dist_m: float | None = None,
) -> CaseRecord:
    if min_dist_m is None:
        min_dist_m = 20.0 if reached_pickup else 350.0
    reader.rides[ride_id] = RideRecord(
        ride_id=ride_id, rider_id=f"USR-R-{ride_id[-6:]}", driver_id=f"USR-D-{ride_id[-6:]}",
        booked_at="2026-09-22T06:00:00Z", status="cancelled",
        quoted_fare_cents=0, charged_fare_cents=fee_cents,
        driver_waited_seconds=waited_seconds,
    )
    reader.routes[ride_id] = RouteRecord(
        ride_id=ride_id, planned_distance_km=0.0, actual_distance_km=0.0,
        planned_duration_s=0, actual_duration_s=0,
    )
    reader.gps[ride_id] = GpsSamples(
        ride_id=ride_id, samples=[], pickup_lat=1.30, pickup_lon=103.85,
        min_distance_to_pickup_m=min_dist_m,
    )
    msgs = []
    if contact_attempt:
        msgs.append(ChatMessage(seq=1, role="driver", at="2026-09-22T06:05:00Z",
                                text="I'm here at pickup", kind="call_attempt"))
    reader.chats[ride_id] = ChatLog(ride_id=ride_id, messages=msgs)
    reader.fares[ride_id] = FareBreakdown(
        ride_id=ride_id,
        components=[FareComponent(name="cancellation", amount_cents=fee_cents)],
        cancellation_fee_cents=fee_cents,
    )
    reader.profiles[reader.rides[ride_id].rider_id] = Profile(
        user_id=reader.rides[ride_id].rider_id, account_age_days=200, avg_rating=4.6,
    )
    reader.profiles[reader.rides[ride_id].driver_id] = Profile(
        user_id=reader.rides[ride_id].driver_id, account_age_days=700, avg_rating=4.7,
    )
    _b = _ev_base(ride_id)
    ev = [
        _ev(f"EV-{_b + 1:06d}", "gps_telemetry", "system_record", "verified",
            {"min_distance_to_pickup_m": min_dist_m, "_question": "arrival"},
            method="device_gps_signed"),
        _ev(f"EV-{_b + 2:06d}", "chat_log", "system_record", "verified",
            {"contact_attempt_recorded": contact_attempt, "_question": "contact"},
            method="platform_log"),
        _ev(f"EV-{_b + 3:06d}", "fare", "system_record", "verified",
            {"cancellation_fee_cents": fee_cents, "_question": "fee"}, method="fare_ledger"),
    ]
    case = CaseRecord(
        case_id=case_id, ride_id=ride_id, category="no_show_charge", filed_by="rider",
        subject="Charged a no-show fee unfairly",
        description="Driver never showed / left early.",
        filed_at="2026-09-22T07:00:00Z", evidence=ev,
    )
    if store is not None:
        store.save_filed_case(case)
    return case


def add_archive(reader: FixtureReader, category: str, n: int = 2) -> None:
    for i in range(n):
        reader.archive.append(
            ArchiveCase(
                archive_case_id=f"DSP-{i+17:06d}", category=category,
                archive_ride_id=f"RIDE-{900017+i:06d}",
                ruling_type="refund", recommended_action="partial refund", confidence=0.8,
                decision_origin="human", policy_version="ryde-policy-0.1.0",
            )
        )
