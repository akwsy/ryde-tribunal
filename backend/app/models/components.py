"""The three model components as thin, provider-driven roles.

Each component builds a prompt from the case (facts + measurements + policy text + the
evidence the role may see), calls the ModelProvider, then post-processes:
  * advocates: validate every citation semantically (I-3) and count invalid ones,
  * judge: receives BOTH advocate outputs plus the case context and returns the ruling.

Provider metadata is stamped on every output (I-6). Nothing here precomputes the verdict; the
provider's judge role does the mapping (I-1).
"""

from __future__ import annotations

from typing import Any

from app.evidence.citation import CitationValidator, invalid_citation_rate
from app.evidence.models import Citation, Evidence
from app.policy.context import PolicyContext
from app.providers.base import ModelProvider


def _visible_evidence_prompt(
    evidence: list[Evidence], party: str
) -> list[dict[str, Any]]:
    """The evidence a party may see, projected to the field the advocate can build a claim on.
    Restricting each advocate to its party's visible evidence keeps the two from sharing state
    (ASSUMPTIONS A-3) and satisfies I-3 check 5 upstream of validation."""
    from app.domain import visible_to

    out: list[dict[str, Any]] = []
    for ev in evidence:
        if not visible_to(ev.visibility, party):
            continue
        field_path, value = _salient_field(ev)
        if field_path is None:
            continue
        out.append(
            {
                "evidence_id": ev.evidence_id,
                "class": ev.class_.value,
                "field_path": field_path,
                "value": value,
                "verification": ev.verification.status.value,
                "undercuts": ev.payload.get("_undercuts"),
            }
        )
    return out


def _salient_field(ev: Evidence) -> tuple[str | None, Any]:
    """Pick the field an advocate would cite from this evidence item."""
    for key in (
        "actual_distance_km",
        "planned_distance_km",
        "deviation_pct",
        "min_distance_to_pickup_m",
        "driver_waited_seconds",
        "contact_attempt_recorded",
        "surge_multiplier",
        "cancellation_fee_cents",
        "text",
    ):
        found, val = ev.field_value(f"payload.{key}")
        if found:
            return key, val
    # Fall back to any single scalar payload field.
    for k, v in ev.payload.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (str, int, float, bool)):
            return k, v
    return None, None


class Advocate:
    def __init__(self, party: str, provider: ModelProvider) -> None:
        self.party = party
        self.provider = provider

    def argue(
        self,
        *,
        category: str,
        policy: PolicyContext,
        evidence: list[Evidence],
        case_id: str,
        currency: str,
    ) -> dict[str, Any]:
        visible = _visible_evidence_prompt(evidence, self.party)
        prompt = {
            "role": f"{self.party}_advocate",
            "party": self.party,
            "category": category,
            "measurements": policy.measurement_map(),
            "policy_rules": [
                {"rule_id": r.rule_id, "text": r.text} for r in policy.applicable_rules
            ],
            "visible_evidence": visible,
            "currency": currency,
        }
        schema = {"argument": "str", "claims": "list", "policy_references": "list"}
        completion = self.provider.complete(prompt, schema)
        data = completion.data

        # Validate every citation (accepted AND rejected) on the same terms (I-3).
        by_id = {ev.evidence_id: ev for ev in evidence}
        validator = CitationValidator(case_id, by_id)
        all_citations: list[Citation] = []
        claim_out: list[dict[str, Any]] = []
        for claim in data.get("claims", []):
            cits = [Citation(**c) for c in claim.get("citations", [])]
            all_citations.extend(cits)
            claim_out.append(
                {
                    "text": claim["text"],
                    "citations": [
                        {
                            "evidence_id": c.evidence_id,
                            "field_path": c.field_path,
                            "observed_value": c.observed_value,
                            "supports": c.supports,
                        }
                        for c in cits
                    ],
                }
            )
        rejected_out: list[dict[str, Any]] = []
        for rej in data.get("rejected_evidence", []):
            rc = Citation(
                evidence_id=rej["evidence_id"],
                field_path=rej.get("field_path", ""),
                observed_value=rej.get("observed_value"),
            )
            all_citations.append(rc)
            rejected_out.append(
                {"evidence_id": rej["evidence_id"], "reason": rej.get("reason", "")}
            )

        results = validator.validate_all(all_citations, self.party)
        invalid_count = sum(1 for r in results if not r.valid)

        return {
            "argument": data["argument"],
            "claims": claim_out,
            "policy_references": data.get("policy_references", []),
            "rejected_evidence": rejected_out,
            "invalid_citation_count": invalid_count,
            "invalid_citation_rate": invalid_citation_rate(results),
            "provider": completion.provider.to_api(policy.policy_version),
            "_synthetic": completion.provider.is_synthetic,
            "_cited_evidence_ids": sorted(
                {c.evidence_id for r in results if r.valid for c in [r.citation]}
            ),
        }


class Judge:
    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider

    def rule(
        self,
        *,
        category: str,
        policy: PolicyContext,
        rider_arg: dict[str, Any],
        driver_arg: dict[str, Any],
        case_facts: dict[str, Any],
        evidence_ids: list[str],
        thresholds: dict[str, float],
        precedence_notes: list[str],
        currency: str,
    ) -> dict[str, Any]:
        m = dict(policy.measurement_map())
        # The Judge also sees underlying fare figures for excess computation.
        ride = case_facts.get("ride") or {}
        fare = case_facts.get("fare") or {}
        m.setdefault("quoted_fare_cents", ride.get("quoted_fare_cents"))
        m.setdefault("charged_fare_cents", ride.get("charged_fare_cents"))
        m.setdefault("cancellation_fee_cents", fare.get("cancellation_fee_cents"))
        prompt = {
            "role": "judge",
            "category": category,
            "measurements": {k: v for k, v in m.items() if v is not None},
            "policy_rules": [
                {"rule_id": r.rule_id, "text": r.text} for r in policy.applicable_rules
            ],
            "thresholds": thresholds,
            "rider_argument": rider_arg["argument"],
            "driver_argument": driver_arg["argument"],
            "evidence_ids": evidence_ids,
            "precedence_notes": precedence_notes,
            "currency": currency,
        }
        schema = {
            "ruling_type": "str",
            "recommended_action": "dict",
            "confidence": "float",
            "reasoning": "str",
            "evidence_references": "list",
            "policy_references": "list",
            "measurements": "dict",
        }
        completion = self.provider.complete(prompt, schema)
        data = dict(completion.data)
        data["provider"] = completion.provider.to_api(policy.policy_version)
        data["_synthetic"] = completion.provider.is_synthetic
        return data
