"""Verified-over-unverified evidence precedence (integrity rule I-7).

Applied PER FACTUAL QUESTION. A `verified` system record (GPS, fare ledger, timestamps)
outranks `unverified` party-submitted text on the same factual question. An `unverified` item
may raise uncertainty, trigger escalation, or support a claim no verified record speaks to —
it may NOT by itself reverse a finding grounded in a verified record.

The Judge asks this layer, for a given factual question, which evidence controls and whether
there is a verified/unverified conflict that must hold-or-escalate rather than flip.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain import VerificationStatus
from app.evidence.models import Evidence

_VERIFIED = {VerificationStatus.verified}
_WEAK = {VerificationStatus.unverified, VerificationStatus.disputed, VerificationStatus.unverifiable}


@dataclass(frozen=True)
class FactualQuestion:
    """A named factual question and the evidence items that speak to it."""

    key: str  # e.g. "driver_reached_pickup", "actual_distance_km"
    speaking_evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class PrecedenceOutcome:
    key: str
    controlling: tuple[Evidence, ...]      # the evidence that decides this question
    outranked: tuple[Evidence, ...]        # weaker evidence on the same question
    conflict: bool                          # verified vs unverified disagreement present
    verified_present: bool
    weak_only: bool                         # only unverified/disputed evidence speaks
    reason: str = ""


class EvidencePrecedence:
    def resolve(
        self, question: FactualQuestion, *, contradicts: set[str] | None = None
    ) -> PrecedenceOutcome:
        """`contradicts` is the set of evidence_ids the caller has determined disagree with
        the verified reading (i.e. an unverified item claiming the opposite)."""
        contradicts = contradicts or set()
        verified = tuple(
            e for e in question.speaking_evidence if e.verification.status in _VERIFIED
        )
        weak = tuple(
            e for e in question.speaking_evidence if e.verification.status in _WEAK
        )
        if verified:
            conflict = any(e.evidence_id in contradicts for e in weak)
            return PrecedenceOutcome(
                key=question.key,
                controlling=verified,
                outranked=weak,
                conflict=conflict,
                verified_present=True,
                weak_only=False,
                reason=(
                    "verified record controls; unverified contradiction may raise "
                    "uncertainty/escalate but cannot flip"
                    if conflict
                    else "verified record controls"
                ),
            )
        # No verified record: weak evidence may support, but the finding is not settled.
        return PrecedenceOutcome(
            key=question.key,
            controlling=weak,
            outranked=(),
            conflict=False,
            verified_present=False,
            weak_only=bool(weak),
            reason="no verified record on this question; weak evidence supports only",
        )
