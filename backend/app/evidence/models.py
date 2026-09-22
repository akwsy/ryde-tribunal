"""Runtime evidence + citation models (contract §4). These are the case-scoped view the
advocates and Judge reason over, built from the DB reader's raw records.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain import EvidenceClass, EvidenceSource, VerificationStatus, Visibility


class Verification(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: VerificationStatus
    method: str = ""
    uncertainty_pct: float = 0.0


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_id: str
    case_id: str
    class_: EvidenceClass = Field(serialization_alias="class")
    source: EvidenceSource
    recorded_at: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    verification: Verification
    visibility: Visibility = Visibility.both
    payload: dict[str, Any] = Field(default_factory=dict)

    def field_value(self, field_path: str) -> tuple[bool, Any]:
        """Resolve a dotted field_path against provenance+payload. Returns (found, value)."""
        root: dict[str, Any] = {"payload": self.payload, "provenance": self.provenance,
                                "recorded_at": self.recorded_at,
                                "verification_status": self.verification.status.value}
        # Allow either "payload.x.y" or a bare "x.y" resolved inside payload.
        parts = field_path.split(".")
        # Try as-is against root first.
        found, val = _walk(root, parts)
        if found:
            return True, val
        # Then treat the whole path as living inside payload.
        return _walk(self.payload, parts)

    def to_api(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "case_id": self.case_id,
            "class": self.class_.value,
            "source": self.source.value,
            "recorded_at": self.recorded_at,
            "provenance": self.provenance,
            "verification": {
                "status": self.verification.status.value,
                "method": self.verification.method,
                "uncertainty_pct": self.verification.uncertainty_pct,
            },
            "visibility": self.visibility.value,
            "payload": self.payload,
        }


def _walk(obj: Any, parts: list[str]) -> tuple[bool, Any]:
    cur = obj
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        elif isinstance(cur, list) and p.isdigit() and int(p) < len(cur):
            cur = cur[int(p)]
        else:
            return False, None
    return True, cur


class Citation(BaseModel):
    """A specific claim reference: which evidence, which field, and the value read (I-3)."""

    model_config = ConfigDict(frozen=True)
    evidence_id: str
    field_path: str
    observed_value: Any
    supports: str = ""  # id of the claim this citation backs


class Claim(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str
    citations: tuple[Citation, ...] = ()
