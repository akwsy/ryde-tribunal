"""Semantic citation validation (integrity rule I-3).

Checking that a cited evidence id EXISTS proves nothing — a model can cite a real record that
does not support its claim. Every citation carries the specific field it relies on and the
value it read, and validation checks all six:

  1. the evidence id exists,
  2. it belongs to THIS case (case_id match),
  3. the cited field_path exists on that record,
  4. the observed_value equals the stored value (within tolerance for floats),
  5. the citing actor was entitled to see it (visibility match),
  6. rejectedEvidence ids are validated on the same terms as accepted ones.

A citation failing any check is recorded as `invalid_citation` and lowers the argument weight.
The metric is `invalid_citation_rate` — never "unsupported claim rate".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import visible_to
from app.evidence.models import Citation, Evidence

FLOAT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class CitationResult:
    citation: Citation
    valid: bool
    reason: str  # "ok" | "missing_evidence" | "wrong_case" | "missing_field" |
    #               "value_mismatch" | "not_visible"


class CitationValidator:
    def __init__(self, case_id: str, evidence_by_id: dict[str, Evidence]) -> None:
        self._case_id = case_id
        self._by_id = evidence_by_id

    def validate(self, citation: Citation, actor: str) -> CitationResult:
        ev = self._by_id.get(citation.evidence_id)
        if ev is None:
            return CitationResult(citation, False, "missing_evidence")  # check 1
        if ev.case_id != self._case_id:
            return CitationResult(citation, False, "wrong_case")  # check 2
        if not visible_to(ev.visibility, actor):
            return CitationResult(citation, False, "not_visible")  # check 5
        found, stored = ev.field_value(citation.field_path)
        if not found:
            return CitationResult(citation, False, "missing_field")  # check 3
        if not _values_equal(citation.observed_value, stored):
            return CitationResult(citation, False, "value_mismatch")  # check 4
        return CitationResult(citation, True, "ok")

    def validate_all(
        self, citations: list[Citation], actor: str
    ) -> list[CitationResult]:
        # check 6 is satisfied by callers passing rejected-evidence citations here too.
        return [self.validate(c, actor) for c in citations]


def _values_equal(a: object, b: object) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= FLOAT_TOLERANCE
    return str(a) == str(b)


def invalid_citation_rate(results: list[CitationResult]) -> float:
    if not results:
        return 0.0
    invalid = sum(1 for r in results if not r.valid)
    return round(invalid / len(results), 3)
