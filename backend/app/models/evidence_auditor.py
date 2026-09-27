"""Audit advocates' claims against the case evidence before the Judge rules."""

from __future__ import annotations

from typing import Any

from app.evidence.models import Evidence
from app.providers.base import ModelOutputInvalid, ModelProvider

_CLASSIFICATIONS = {
    "contradicted", "incorrect", "fabrication_suspected", "unsupported", "consistent", "inconclusive"
}
_MATERIALITY = {"material", "non_material", "unknown"}
_SCHEMA = {
    "type": "object",
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["party", "claim_text", "classification", "confidence",
                             "explanation", "evidence_references", "materiality"],
                "properties": {
                    "party": {"type": "string", "enum": ["rider", "driver"]},
                    "claim_text": {"type": "string", "minLength": 1},
                    "classification": {"type": "string", "enum": sorted(_CLASSIFICATIONS)},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "explanation": {"type": "string", "minLength": 1},
                    "evidence_references": {"type": "array", "items": {"type": "string"}},
                    "materiality": {"type": "string", "enum": sorted(_MATERIALITY)},
                },
                "additionalProperties": False,
            },
        }
    },
    "additionalProperties": False,
}


class EvidenceAuditor:
    """Use the configured provider to flag claims needing closer judicial scrutiny.

    Findings are advisory signals. The caller supplies them to the Judge and never treats a
    fraud or fabrication allegation as independently sufficient for escalation.
    """

    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider

    def audit(
        self,
        *,
        rider: dict[str, Any],
        driver: dict[str, Any],
        evidence: list[Evidence],
        category: str,
        policy_rules: list[dict[str, str]],
    ) -> dict[str, Any]:
        prompt = {
            "role": "evidence_auditor",
            "instruction": (
                "Compare each advocate claim with the cited evidence and with the other party's "
                "claims. Report concrete contradictions, factual mismatches, possible fabrication, "
                "and unsupported claims. Do not infer fabrication merely from missing evidence. "
                "Treat verified records as stronger than unverified submissions. Findings are "
                "advisory and do not decide or escalate the case by themselves. For every "
                "contradicted, incorrect, or fabrication_suspected finding, label materiality "
                "against the supplied case category and policy: material, non_material, or unknown. "
                "Use unknown if you cannot determine whether it could affect the ruling."
            ),
            "category": category,
            "policy_rules": policy_rules,
            "advocates": {"rider": rider, "driver": driver},
            "evidence": [item.to_api() for item in evidence],
        }
        completion = self.provider.complete(prompt, _SCHEMA)
        data = completion.data
        findings = data.get("findings") if isinstance(data, dict) else None
        if not isinstance(findings, list):
            raise ModelOutputInvalid("evidence audit findings must be a list")
        allowed_ids = {item.evidence_id for item in evidence}
        for party_data in (rider, driver):
            for claim in party_data.get("claims", []):
                for citation in claim.get("citations", []):
                    if isinstance(citation, dict) and isinstance(citation.get("evidence_id"), str):
                        allowed_ids.add(citation["evidence_id"])
        clean: list[dict[str, Any]] = []
        for index, item in enumerate(findings):
            if not isinstance(item, dict):
                raise ModelOutputInvalid(f"evidence audit finding {index} must be an object")
            party = item.get("party")
            classification = item.get("classification")
            if classification not in _CLASSIFICATIONS or party not in {"rider", "driver"}:
                raise ModelOutputInvalid(f"evidence audit finding {index} has invalid classification")
            materiality = item.get("materiality")
            if materiality not in _MATERIALITY:
                raise ModelOutputInvalid(f"evidence audit finding {index} has invalid materiality")
            claim_text = item.get("claim_text")
            explanation = item.get("explanation")
            confidence = item.get("confidence")
            evidence_ids = item.get("evidence_references")
            party_claims = (rider if party == "rider" else driver).get("claims", [])
            if not isinstance(claim_text, str) or not any(
                isinstance(claim, dict) and claim.get("text") == claim_text
                for claim in party_claims
            ):
                raise ModelOutputInvalid(f"evidence audit finding {index} cites an unknown claim")
            if not isinstance(explanation, str) or not explanation.strip():
                raise ModelOutputInvalid(f"evidence audit finding {index} has empty explanation")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise ModelOutputInvalid(f"evidence audit finding {index} has invalid confidence")
            if not isinstance(evidence_ids, list) or any(not isinstance(x, str) for x in evidence_ids):
                raise ModelOutputInvalid(f"evidence audit finding {index} has invalid evidence references")
            if any(evidence_id not in allowed_ids for evidence_id in evidence_ids):
                raise ModelOutputInvalid(f"evidence audit finding {index} cites unknown evidence")
            clean.append({
                "party": party,
                "claim_text": claim_text,
                "classification": classification,
                "confidence": float(confidence),
                "explanation": explanation.strip(),
                "evidence_references": evidence_ids,
                "materiality": materiality,
            })
        return {"findings": clean, "provider": completion.provider.to_api()}
