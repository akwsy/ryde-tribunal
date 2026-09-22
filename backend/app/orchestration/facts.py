"""Assemble denormalized case facts + runtime Evidence from the DB accessors.

Everything the model components reason over is built here from the nine accessors. Case facts
carry NO outcome fields (I-2 is the DB's guarantee; we do not synthesize any either). A
malformed record surfaces as uncertainty downstream, never as fact (brief §7).
"""

from __future__ import annotations

from typing import Any

from app.domain import (
    EvidenceClass,
    EvidenceSource,
    VerificationStatus,
    Visibility,
)
from app.evidence.models import Evidence, Verification
from app.persistence.reader import DatabaseReader, DatabaseUnavailable


class MalformedRecord(Exception):
    """A record could not be interpreted; the case becomes uncertain, not false-fact."""


def assemble_facts(reader: DatabaseReader, case) -> dict[str, Any]:
    ride = reader.get_ride(case.ride_id)
    route = reader.get_route(case.ride_id)
    gps = reader.get_gps_samples(case.ride_id)
    chat = reader.get_chat_log(case.ride_id)
    fare = reader.get_fare_breakdown(case.ride_id)
    rider_profile = reader.get_profile(ride.rider_id) if ride else None
    driver_profile = reader.get_profile(ride.driver_id) if ride else None

    return {
        "ride": ride.model_dump() if ride else {},
        "route": route.model_dump() if route else {},
        "gps": gps.model_dump() if gps else {},
        "chat": chat.model_dump() if chat else {},
        "fare": fare.model_dump() if fare else {},
        "rider_profile": rider_profile.model_dump() if rider_profile else {},
        "driver_profile": driver_profile.model_dump() if driver_profile else {},
    }


def build_evidence(case) -> list[Evidence]:
    """Turn the case's PARTY-SUBMITTED evidence refs into runtime Evidence. A ref that cannot
    be parsed is dropped with a marker rather than fabricated into a fact. System-record
    evidence is added separately by `assemble_evidence_bundle`."""
    out: list[Evidence] = []
    for ref in case.evidence:
        try:
            out.append(
                Evidence(
                    evidence_id=ref.evidence_id,
                    case_id=case.case_id,
                    class_=EvidenceClass(getattr(ref, "class_", None) or ref.model_dump().get("class_", "attachment")),
                    source=EvidenceSource(ref.source),
                    recorded_at=ref.recorded_at,
                    provenance=ref.provenance,
                    verification=Verification(
                        status=VerificationStatus(ref.verification_status),
                        method=ref.verification_method,
                        uncertainty_pct=ref.verification_uncertainty_pct,
                    ),
                    visibility=Visibility(ref.visibility),
                    payload=ref.payload,
                )
            )
        except (ValueError, KeyError):
            # Malformed → represent as an unverifiable marker so it raises uncertainty.
            out.append(
                Evidence(
                    evidence_id=getattr(ref, "evidence_id", "EV-MALFORMED"),
                    case_id=case.case_id,
                    class_=EvidenceClass.attachment,
                    source=EvidenceSource.system_record,
                    verification=Verification(status=VerificationStatus.unverifiable,
                                              method="parse_failed"),
                    visibility=Visibility.reviewer_only,
                    payload={"_malformed": True},
                )
            )
    return out


def assemble_evidence_bundle(reader: DatabaseReader, case) -> list[Evidence]:
    """Assemble the case's evidence bundle at adjudication time (docs/02-api-contract.md §6):
    VERIFIED system records from `ride_data` reads + party submissions from the filed case.

    Every system record becomes an `Evidence` with a stable `EV-\\d{6}` id, `case_id` set to the
    live case, `source: system_record`, `verification.status: verified` with a method, correct
    `visibility`, `provenance` naming the source table + row ids, and a `payload` carrying the
    salient fields (keyed so the advocates can cite `field_path`/`observed_value` and I-3 can
    validate them, and `_question` so I-7 precedence can group by factual question).

    This is what was missing in the real path: the fixture builders hand-populated evidence,
    but nothing assembled it from the reader.
    """
    facts = assemble_facts(reader, case)
    ride = facts.get("ride") or {}
    route = facts.get("route") or {}
    gps = facts.get("gps") or {}
    chat = facts.get("chat") or {}
    fare = facts.get("fare") or {}

    bundle: list[Evidence] = []
    seq = 0
    # Evidence ids are stable AND case-unique: a per-ride base offset (from the ride id's
    # numeric part) keeps two different rides on disjoint EV-\d{6} ranges, so distinct cases
    # cite distinct evidence-id sets (I-5) while each case's ids stay stable across runs.
    import re as _re
    _digits = _re.sub(r"\D", "", case.ride_id) or "0"
    _base = (int(_digits) % 100000) * 10  # room for up to 10 records per case

    def _sys(cls: EvidenceClass, table: str, row_ids: list[str], payload: dict,
             method: str, visibility: Visibility = Visibility.both,
             recorded_at: str = "") -> None:
        nonlocal seq
        seq += 1
        bundle.append(
            Evidence(
                evidence_id=f"EV-{_base + seq:06d}",
                case_id=case.case_id,
                class_=cls,
                source=EvidenceSource.system_record,
                recorded_at=recorded_at or ride.get("booked_at", ""),
                provenance={"table": table, "row_ids": row_ids, "collector": "database.reader"},
                verification=Verification(status=VerificationStatus.verified, method=method),
                visibility=visibility,
                payload=payload,
            )
        )

    rid = case.ride_id

    # Route telemetry — distances (the deciding facts for route_deviation).
    if route:
        _sys(
            EvidenceClass.gps_telemetry, "ride_data.ride_routes", [rid],
            {
                "actual_distance_km": route.get("actual_distance_km"),
                "planned_distance_km": route.get("planned_distance_km"),
                "actual_duration_s": route.get("actual_duration_s"),
                "planned_duration_s": route.get("planned_duration_s"),
                "_question": "distance",
            },
            method="device_gps_signed",
        )
        # Unexplained stops, if any.
        longest = 0
        for s in route.get("stops", []) or []:
            if not s.get("rider_requested", False):
                longest = max(longest, int(s.get("duration_s", 0) or 0))
        if route.get("stops"):
            _sys(
                EvidenceClass.gps_telemetry, "ride_data.ride_route_stops", [rid],
                {"longest_unexplained_stop_s": longest, "_question": "stops"},
                method="device_gps_signed",
            )

    # GPS samples + closest approach to pickup (deciding fact for no_show).
    if gps:
        min_d = gps.get("min_distance_to_pickup_m")
        n = len(gps.get("samples", []) or [])
        _sys(
            EvidenceClass.gps_telemetry, "ride_data.ride_gps_samples", [rid],
            {"min_distance_to_pickup_m": min_d, "sample_count": n, "_question": "arrival"},
            method="device_gps_signed",
        )

    # Fare ledger — the charged/quoted figures and cancellation fee.
    if fare or ride:
        _sys(
            EvidenceClass.fare, "ride_data.ride_fare_breakdowns", [rid],
            {
                "quoted_fare_cents": ride.get("quoted_fare_cents"),
                "charged_fare_cents": ride.get("charged_fare_cents"),
                "cancellation_fee_cents": fare.get("cancellation_fee_cents"),
                "surge_multiplier": fare.get("surge_multiplier"),
                "_question": "fare",
            },
            method="fare_ledger",
        )

    # Chat log — contact attempts (deciding fact for no_show) + safety signals.
    if chat:
        msgs = chat.get("messages", []) or []
        contact = any(
            m.get("kind") == "call_attempt" or m.get("role") == "driver" for m in msgs
        )
        _sys(
            EvidenceClass.chat_log, "ride_data.ride_chat_messages", [rid],
            {"contact_attempt_recorded": contact, "message_count": len(msgs),
             "_question": "contact"},
            method="platform_log",
        )
        # Waiting time lives on the ride header (folded from route by the adapter).
        if ride.get("driver_waited_seconds") is not None:
            _sys(
                EvidenceClass.gps_telemetry, "ride_data.rides", [rid],
                {"driver_waited_seconds": ride.get("driver_waited_seconds"),
                 "_question": "arrival"},
                method="device_gps_signed",
            )

    # Party submissions from the filed dispute join the same bundle (unverified).
    bundle.extend(build_evidence(case))
    return bundle

