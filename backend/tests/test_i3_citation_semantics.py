"""I-3 — citation validation is semantic, not referential.

The load-bearing case: an advocate cites a REAL, same-case record whose stored value
CONTRADICTS the claimed value. Referential checking (id exists) passes; semantic checking
must reject it as value_mismatch. All six checks are exercised.
"""

from __future__ import annotations

from app.domain import (
    EvidenceClass,
    EvidenceSource,
    VerificationStatus,
    Visibility,
)
from app.evidence.citation import CitationValidator, invalid_citation_rate
from app.evidence.models import Citation, Evidence, Verification


def _ev(evidence_id, case_id, payload, visibility="both"):
    return Evidence(
        evidence_id=evidence_id, case_id=case_id,
        class_=EvidenceClass.gps_telemetry, source=EvidenceSource.system_record,
        verification=Verification(status=VerificationStatus.verified, method="gps"),
        visibility=Visibility(visibility), payload=payload,
    )


def _validator(case_id="DSP-1", evs=None):
    evs = evs or []
    return CitationValidator(case_id, {e.evidence_id: e for e in evs})


def test_real_record_contradicting_claim_is_invalid():
    ev = _ev("EV-1", "DSP-1", {"actual_distance_km": 18.4})
    v = _validator(evs=[ev])
    # Advocate cites a REAL, same-case record but claims a value it does not hold.
    bad = Citation(evidence_id="EV-1", field_path="payload.actual_distance_km",
                   observed_value=11.0, supports="c1")
    res = v.validate(bad, actor="rider")
    assert res.valid is False and res.reason == "value_mismatch"


def test_matching_value_is_valid_within_float_tolerance():
    ev = _ev("EV-1", "DSP-1", {"actual_distance_km": 18.4})
    v = _validator(evs=[ev])
    good = Citation(evidence_id="EV-1", field_path="payload.actual_distance_km",
                    observed_value=18.4000001, supports="c1")
    assert v.validate(good, actor="rider").valid is True


def test_missing_evidence_id():
    v = _validator(evs=[])
    c = Citation(evidence_id="EV-NOPE", field_path="payload.x", observed_value=1)
    assert v.validate(c, "rider").reason == "missing_evidence"


def test_wrong_case():
    ev = _ev("EV-1", "DSP-OTHER", {"x": 1})
    v = _validator(case_id="DSP-1", evs=[ev])
    c = Citation(evidence_id="EV-1", field_path="payload.x", observed_value=1)
    assert v.validate(c, "rider").reason == "wrong_case"


def test_missing_field():
    ev = _ev("EV-1", "DSP-1", {"x": 1})
    v = _validator(evs=[ev])
    c = Citation(evidence_id="EV-1", field_path="payload.y", observed_value=1)
    assert v.validate(c, "rider").reason == "missing_field"


def test_visibility_denied():
    ev = _ev("EV-1", "DSP-1", {"x": 1}, visibility="driver_only")
    v = _validator(evs=[ev])
    c = Citation(evidence_id="EV-1", field_path="payload.x", observed_value=1)
    assert v.validate(c, "rider").reason == "not_visible"


def test_rejected_evidence_validated_on_same_terms():
    # check 6: a rejectedEvidence citation is run through the same validator.
    ev = _ev("EV-1", "DSP-1", {"x": 5})
    v = _validator(evs=[ev])
    rejected = Citation(evidence_id="EV-1", field_path="payload.x", observed_value=99)
    assert v.validate(rejected, "rider").reason == "value_mismatch"


def test_invalid_citation_rate_metric():
    ev = _ev("EV-1", "DSP-1", {"x": 5})
    v = _validator(evs=[ev])
    results = v.validate_all(
        [
            Citation(evidence_id="EV-1", field_path="payload.x", observed_value=5),   # ok
            Citation(evidence_id="EV-1", field_path="payload.x", observed_value=6),   # mismatch
        ],
        "rider",
    )
    assert invalid_citation_rate(results) == 0.5
