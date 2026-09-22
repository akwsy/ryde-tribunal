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
    """Turn the case's evidence refs into runtime Evidence. A ref that cannot be parsed is
    dropped with a marker rather than fabricated into a fact."""
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
