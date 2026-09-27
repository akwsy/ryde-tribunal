"""Assemble denormalized case facts + runtime Evidence from the DB accessors.

Everything the model components reason over is built here from the nine accessors. Case facts
carry NO outcome fields (I-2 is the DB's guarantee; we do not synthesize any either). A
malformed record surfaces as uncertainty downstream, never as fact (brief §7).
"""

from __future__ import annotations

from typing import Any, Callable

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
    app_event_reader = getattr(reader, "get_app_events", None)
    app_events = app_event_reader(case.ride_id) if app_event_reader else []
    fare = reader.get_fare_breakdown(case.ride_id)
    rider_profile = reader.get_profile(ride.rider_id) if ride else None
    driver_profile = reader.get_profile(ride.driver_id) if ride else None

    return {
        "ride": ride.model_dump() if ride else {},
        "route": route.model_dump() if route else {},
        "gps": gps.model_dump() if gps else {},
        "chat": chat.model_dump() if chat else {},
        "app_events": [event.model_dump() for event in app_events],
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


def assemble_evidence_bundle(
    reader: DatabaseReader,
    case,
    allocate_evidence_id: Callable[[], str] | None = None,
    *,
    facts: dict[str, Any] | None = None,
) -> list[Evidence]:
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
    # The orchestrator already assembles facts for policy evaluation. Reuse that snapshot
    # here so one adjudication does not repeat the same set of database reads.
    if facts is None:
        facts = assemble_facts(reader, case)
    ride = facts.get("ride") or {}
    route = facts.get("route") or {}
    gps = facts.get("gps") or {}
    chat = facts.get("chat") or {}
    fare = facts.get("fare") or {}
    app_events = facts.get("app_events") or []

    bundle: list[Evidence] = []
    # Production orchestration provides a database-backed global sequence. The fallback is
    # scoped to the case for direct helper use in tests; production IDs never derive from
    # company-provided trip identifiers.
    import re as _re
    _case_digits = _re.sub(r"\D", "", case.case_id) or "0"
    _local_seq = 0

    def _new_id() -> str:
        nonlocal _local_seq
        if allocate_evidence_id is not None:
            return allocate_evidence_id()
        _local_seq += 1
        return f"EV-{(int(_case_digits) * 100 + _local_seq) % 1_000_000:06d}"

    def _meta(record: dict[str, Any] | None, table: str, row_ids: list[str]) -> dict[str, Any]:
        record = record or {}
        synthetic = bool(record.get("synthetic", True))
        status = record.get("verification_status")
        if not status:
            status = "verified" if synthetic else "unverified"
        source_name = record.get("evidence_source")
        valid_sources = {item.value for item in EvidenceSource}
        source = source_name if source_name in valid_sources else (
            "system_record" if synthetic else "company_imported"
        )
        provenance = record.get("provenance") or {
            "table": table, "row_ids": row_ids, "collector": "database.reader"
        }
        method = record.get("verified_by") or source_name or (
            "seeded_system_record" if synthetic else "source_record_unverified"
        )
        return {"status": status, "source": source, "provenance": provenance,
                "method": method}

    def _combined_meta(records: list[dict[str, Any]], table: str,
                       row_ids: list[str]) -> dict[str, Any]:
        metadata = [_meta(row, table, row_ids) for row in records]
        if not metadata:
            return _meta(None, table, row_ids)
        statuses = [m["status"] for m in metadata]
        # A derived fact is only verified when every contributing row is verified.
        status = "verified" if all(s == "verified" for s in statuses) else (
            "disputed" if "disputed" in statuses else
            "unverifiable" if "unverifiable" in statuses else "unverified"
        )
        return {
            "status": status,
            "source": "company_imported" if any(m["source"] == "company_imported" for m in metadata)
                     else "system_record",
            "provenance": {"derived_from": [m["provenance"] for m in metadata]},
            "method": "all_source_records_verified" if status == "verified" else "source_rows_not_all_verified",
        }

    def _sys(cls: EvidenceClass, table: str, row_ids: list[str], payload: dict,
             method: str, visibility: Visibility = Visibility.both,
             recorded_at: str = "", metadata: dict[str, Any] | None = None) -> None:
        meta = metadata or _meta(None, table, row_ids)
        bundle.append(
            Evidence(
                evidence_id=_new_id(),
                case_id=case.case_id,
                class_=cls,
                source=EvidenceSource(meta["source"]),
                recorded_at=recorded_at or ride.get("booked_at", ""),
                provenance=meta["provenance"],
                verification=Verification(status=VerificationStatus(meta["status"]),
                                          method=meta.get("method") or method),
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
            metadata=_meta(route, "ride_data.ride_routes", [rid]),
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
                metadata=_meta(route, "ride_data.ride_route_stops", [rid]),
            )

    # GPS samples + closest approach to pickup (deciding fact for no_show_charge).
    if gps:
        min_d = gps.get("min_distance_to_pickup_m")
        n = len(gps.get("samples", []) or [])
        gps_rows = gps.get("samples", []) or []
        _sys(
            EvidenceClass.gps_telemetry, "ride_data.ride_gps_samples", [rid],
            {"min_distance_to_pickup_m": min_d, "sample_count": n, "_question": "arrival"},
            method="device_gps_signed",
            metadata=_combined_meta(gps_rows, "ride_data.ride_gps_samples", [rid]),
        )
        for sample in gps_rows:
            _sys(
                EvidenceClass.gps_telemetry, "ride_data.ride_gps_samples",
                [str(sample.get("sample_id") or sample.get("seq"))],
                {"sequence_no": sample.get("seq"), "latitude": sample.get("lat"),
                 "longitude": sample.get("lon"), "accuracy_m": sample.get("accuracy_m"),
                 "status": sample.get("status"), "_question": "arrival"},
                method="device_gps_signed", recorded_at=sample.get("at", ""),
                metadata=_meta(sample, "ride_data.ride_gps_samples", [rid]),
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
            metadata=_combined_meta([ride, fare], "ride_data.ride_fare_breakdowns", [rid]),
        )

    # Chat log — contact attempts (deciding fact for no_show_charge) + safety signals.
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
            metadata=_combined_meta(msgs, "ride_data.ride_chat_messages", [rid]),
        )
        for message in msgs:
            _sys(
                EvidenceClass.chat_log, "ride_data.ride_chat_messages",
                [str(message.get("message_id") or message.get("seq"))],
                {"sequence_no": message.get("seq"), "role": message.get("role"),
                 "kind": message.get("event_type") or message.get("kind"),
                 "status": message.get("status"), "text": message.get("text"),
                 "_question": "contact"},
                method="platform_log", recorded_at=message.get("at", ""),
                metadata=_meta(message, "ride_data.ride_chat_messages", [rid]),
            )
        # Waiting time lives on the ride header (folded from route by the adapter).
        if ride.get("driver_waited_seconds") is not None:
            _sys(
                EvidenceClass.gps_telemetry, "ride_data.rides", [rid],
                {"driver_waited_seconds": ride.get("driver_waited_seconds"),
                 "_question": "arrival"},
                method="device_gps_signed",
                metadata=_meta(ride, "ride_data.rides", [rid]),
            )

    for event in app_events:
        _sys(
            EvidenceClass.app_event, "ride_data.ride_app_events",
            [str(event.get("event_id"))],
            {"sequence_no": event.get("sequence_no"), "event_type": event.get("event_type"),
             "details": event.get("details"), "_question": "app_event"},
            method="platform_event_log", recorded_at=event.get("event_at", ""),
            metadata=_meta(event, "ride_data.ride_app_events", [rid]),
        )

    # Party submissions from the filed dispute join the same bundle (unverified).
    bundle.extend(build_evidence(case))
    return bundle
