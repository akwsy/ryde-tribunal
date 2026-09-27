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

from pydantic import ValidationError

from app.evidence.citation import CitationValidator, invalid_citation_rate
from app.evidence.models import Citation, Evidence
from app.policy.context import PolicyContext
from app.providers.base import ModelOutputInvalid, ModelProvider


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelOutputInvalid(f"{where} must be an object")
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelOutputInvalid(f"{where} must be a non-empty string")
    return value


def _string_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ModelOutputInvalid(f"{where} must be a list of strings")
    return value


_CITATION_SCHEMA = {
    "type": "object",
    "required": ["evidence_id", "field_path", "observed_value", "supports"],
    "properties": {
        "evidence_id": {"type": "string", "minLength": 1},
        "field_path": {"type": "string", "minLength": 1},
        "observed_value": {},
        "supports": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}
_ADVOCATE_SCHEMA = {
    "type": "object",
    "required": ["argument", "claims", "policy_references", "rejected_evidence"],
    "properties": {
        "argument": {"type": "string", "minLength": 1},
        "claims": {"type": "array", "items": {
            "type": "object", "required": ["text", "citations"],
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string", "minLength": 1},
                "citations": {"type": "array", "items": _CITATION_SCHEMA},
            }, "additionalProperties": False,
        }},
        "policy_references": {"type": "array", "items": {"type": "string"}},
        "rejected_evidence": {"type": "array", "items": {
            "type": "object", "required": ["evidence_id", "reason"],
            "properties": {
                "evidence_id": {"type": "string", "minLength": 1},
                "field_path": {"type": "string"},
                "observed_value": {},
                "reason": {"type": "string", "minLength": 1},
            }, "additionalProperties": False,
        }},
    },
    "additionalProperties": False,
}


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
        "event_type",
        "details",
        "status",
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
        schema = _ADVOCATE_SCHEMA
        completion = self.provider.complete(prompt, schema)
        data = _object(completion.data, "advocate response")
        _string(data.get("argument"), "advocate.argument")
        claims = data.get("claims")
        if not isinstance(claims, list):
            raise ModelOutputInvalid("advocate.claims must be a list")
        for i, claim in enumerate(claims):
            claim = _object(claim, f"advocate.claims[{i}]")
            _string(claim.get("text"), f"advocate.claims[{i}].text")
            citations = claim.get("citations", [])
            if not isinstance(citations, list):
                raise ModelOutputInvalid(f"advocate.claims[{i}].citations must be a list")
            for j, citation in enumerate(citations):
                citation = _object(citation, f"advocate.claims[{i}].citations[{j}]")
                for field in ("evidence_id", "field_path", "supports"):
                    _string(citation.get(field), f"citation.{field}")
                if "observed_value" not in citation:
                    raise ModelOutputInvalid("citation.observed_value is required")
        _string_list(data.get("policy_references", []), "advocate.policy_references")
        rejected = data.get("rejected_evidence", [])
        if not isinstance(rejected, list):
            raise ModelOutputInvalid("advocate.rejected_evidence must be a list")
        for item in rejected:
            item = _object(item, "advocate.rejected_evidence item")
            _string(item.get("evidence_id"), "rejected_evidence.evidence_id")
            _string(item.get("reason"), "rejected_evidence.reason")

        # Validate every citation (accepted AND rejected) on the same terms (I-3), and attach
        # the REQUIRED `valid` boolean to each emitted citation (contract §Citation; FIX 2).
        by_id = {ev.evidence_id: ev for ev in evidence}
        validator = CitationValidator(case_id, by_id)
        all_results: list = []
        claim_out: list[dict[str, Any]] = []
        for claim in data.get("claims", []):
            try:
                cits = [Citation(**c) for c in claim.get("citations", [])]
            except ValidationError as exc:
                raise ModelOutputInvalid(f"invalid advocate citation: {exc}") from exc
            cit_out = []
            for c in cits:
                res = validator.validate(c, self.party)
                all_results.append(res)
                cit_out.append(
                    {
                        "evidence_id": c.evidence_id,
                        "field_path": c.field_path,
                        "observed_value": c.observed_value,
                        "supports": c.supports,
                        "valid": res.valid,  # REQUIRED, never omitted
                    }
                )
            claim_out.append({"text": claim["text"], "citations": cit_out})
        rejected_out: list[dict[str, Any]] = []
        for rej in data.get("rejected_evidence", []):
            try:
                rc = Citation(
                    evidence_id=rej["evidence_id"],
                    field_path=rej.get("field_path", ""),
                    observed_value=rej.get("observed_value"),
                )
            except ValidationError as exc:
                raise ModelOutputInvalid(f"invalid rejected evidence citation: {exc}") from exc
            all_results.append(validator.validate(rc, self.party))
            rejected_out.append(
                {"evidence_id": rej["evidence_id"], "reason": rej.get("reason", "")}
            )

        results = all_results
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
        extra_measurements: dict[str, Any] | None = None,
        precedents: list[dict[str, Any]] | None = None,
        evidence_audit: list[dict[str, Any]] | None = None,
        fraud_assessment: dict[str, Any] | None = None,
        judging_weights: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        m = dict(policy.measurement_map())
        # The Judge also sees underlying fare figures for excess computation.
        ride = case_facts.get("ride") or {}
        fare = case_facts.get("fare") or {}
        m.setdefault("quoted_fare_cents", ride.get("quoted_fare_cents"))
        m.setdefault("charged_fare_cents", ride.get("charged_fare_cents"))
        m.setdefault("cancellation_fee_cents", fare.get("cancellation_fee_cents"))
        if extra_measurements:
            m.update(extra_measurements)
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
            "evidence_audit": evidence_audit or [],
            "fraud_assessment": fraud_assessment or {},
            # Historical outcomes are advisory. Human-approved outcomes are marked as
            # higher credibility than model proposals, but neither is binding.
            "precedents": precedents or [],
            "judging_weights": judging_weights or {},
            "precedence_order": (
                "Apply the current policy first. Use precedent only when policy and current-case "
                "evidence permit; among precedents, prefer more recent decisions and give a "
                "reviewer-approved ruling more weight than a model-proposed ruling."
            ),
            "precedent_instruction": (
                "Treat precedent as advisory only. Give human-approved precedent more weight "
                "than a model proposal, but justify this ruling independently from this case's "
                "evidence and policy."
            ),
            "currency": currency,
            "decisive_fact_instruction": (
                "List every factual proposition that materially determines the ruling. For each, "
                "identify only evidence IDs that concretely support that fact. Do not omit a "
                "decisive fact and do not cite an ID that does not support it. If the record "
                "cannot establish a decisive fact, return an empty evidence_references list for "
                "that fact; the case will require human review."
            ),
        }
        schema = {
            "type": "object",
            "required": ["ruling_type", "recommended_action", "confidence", "reasoning",
                         "evidence_references", "policy_references", "measurements",
                         "decisive_facts"],
            "properties": {
                "ruling_type": {"type": "string", "enum": ["refund", "compensation", "no_action"]},
                "recommended_action": {"type": "object"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string", "minLength": 1},
                "evidence_references": {"type": "array", "items": {"type": "string"}},
                "policy_references": {"type": "array", "items": {"type": "string"}},
                "measurements": {"type": "object"},
                "decisive_facts": {"type": "array", "items": {
                    "type": "object",
                    "required": ["fact", "evidence_references"],
                    "properties": {
                        "fact": {"type": "string", "minLength": 1},
                        "evidence_references": {"type": "array", "items": {
                            "type": "string", "minLength": 1,
                        }},
                    },
                    "additionalProperties": False,
                }},
            },
            "additionalProperties": False,
        }
        completion = self.provider.complete(prompt, schema)
        data = _object(completion.data, "judge response")
        if data.get("ruling_type") not in {"refund", "compensation", "no_action"}:
            raise ModelOutputInvalid("judge.ruling_type is invalid")
        _object(data.get("recommended_action"), "judge.recommended_action")
        confidence = data.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ModelOutputInvalid("judge.confidence must be between 0 and 1")
        _string(data.get("reasoning"), "judge.reasoning")
        _string_list(data.get("evidence_references"), "judge.evidence_references")
        _string_list(data.get("policy_references"), "judge.policy_references")
        _object(data.get("measurements"), "judge.measurements")
        decisive_facts = data.get("decisive_facts")
        if not isinstance(decisive_facts, list):
            raise ModelOutputInvalid("judge.decisive_facts must be a list")
        allowed_evidence_ids = set(evidence_ids)
        for index, item in enumerate(decisive_facts):
            if not isinstance(item, dict):
                raise ModelOutputInvalid(f"judge.decisive_facts[{index}] must be an object")
            fact = item.get("fact")
            references = item.get("evidence_references")
            if not isinstance(fact, str) or not fact.strip():
                raise ModelOutputInvalid(f"judge.decisive_facts[{index}].fact must be non-empty")
            if not isinstance(references, list) or any(
                not isinstance(reference, str) or not reference for reference in references
            ):
                raise ModelOutputInvalid(
                    f"judge.decisive_facts[{index}].evidence_references must be a list of IDs"
                )
            if any(reference not in allowed_evidence_ids for reference in references):
                raise ModelOutputInvalid(
                    f"judge.decisive_facts[{index}] cites an unknown evidence ID"
                )
        if any(reference not in allowed_evidence_ids for reference in data["evidence_references"]):
            raise ModelOutputInvalid("judge.evidence_references contains an unknown evidence ID")
        data = dict(data)
        data["provider"] = completion.provider.to_api(policy.policy_version)
        data["_synthetic"] = completion.provider.is_synthetic
        return data
