"""Provider-backed, case-specific fraud-risk assessment for the Judge."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.evidence.models import Evidence
from app.providers.base import ModelOutputInvalid, ModelProvider

_FINDING_TYPES = {
    "prior_dispute_density", "claim_evidence_mismatch",
    "unsupported_claim_pattern", "potentially_fabricated_reference",
}
_SOURCE_FIELDS = {
    "profile_history.disputes_last_30d", "profile_history.disputes_total",
    "profile_history.fraud_flag_count", "profile_history.prior_classifications",
    "advocate_claims", "advocate_claims.citation.evidence_id",
}
_SCHEMA = {
    "type": "object",
    "required": ["risk_score", "confidence", "findings"],
    "properties": {
        "risk_score": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["finding_type", "party", "summary", "source_fields", "evidence_ids"],
                "properties": {
                    "finding_type": {"type": "string", "enum": sorted(_FINDING_TYPES)},
                    "party": {"type": "string", "enum": ["rider", "driver", "both", "unknown"]},
                    "summary": {"type": "string", "minLength": 1},
                    "source_fields": {"type": "array", "items": {"type": "string"}},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


class FraudDetector:
    """Assess indicators and uncertainty; it does not declare guilt or decide escalation."""

    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider

    def assess(
        self,
        *,
        party: str,
        profile: dict[str, Any] | None,
        evidence: list[Evidence],
        evidence_audit: list[dict[str, Any]],
        advocate_claims: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = {
            "role": "fraud_detector",
            "party": party,
            "profile_history": _fraud_relevant_profile(profile or {}),
            "evidence": [item.to_api() for item in evidence],
            "allowed_source_fields": sorted(_SOURCE_FIELDS),
            "allowed_evidence_ids": sorted(item.evidence_id for item in evidence),
            "evidence_audit": evidence_audit,
            "advocate_claims": advocate_claims,
            "instructions": (
                "Estimate fraud risk from case-specific indicators, not protected or irrelevant "
                "traits. Prior dispute history is a weak signal, not proof. Distinguish factual "
                "mismatches and unsupported submissions from intent. Cite profile fields and evidence "
                "IDs used. source_fields must be copied exactly from allowed_source_fields; do not "
                "put trip fields, policy IDs, classifications, or evidence IDs in source_fields. "
                "evidence_ids must be copied exactly from allowed_evidence_ids. If there is no "
                "supported indicator, return an empty findings list. Do not recommend or trigger "
                "escalation; the Judge weighs this assessment. Verified records cannot be displaced "
                "by risk indicators."
            ),
        }
        schema = deepcopy(_SCHEMA)
        schema["properties"]["findings"]["items"]["properties"]["source_fields"]["items"]["enum"] = sorted(_SOURCE_FIELDS)
        schema["properties"]["findings"]["items"]["properties"]["evidence_ids"]["items"]["enum"] = sorted(
            item.evidence_id for item in evidence
        )
        completion = self.provider.complete(prompt, schema)
        data = completion.data
        if not isinstance(data, dict):
            raise ModelOutputInvalid("fraud assessment must be an object")
        score = data.get("risk_score")
        confidence = data.get("confidence")
        if not _probability(score) or not _probability(confidence):
            raise ModelOutputInvalid("fraud risk_score and confidence must be between 0 and 1")
        findings = data.get("findings")
        if not isinstance(findings, list):
            raise ModelOutputInvalid("fraud findings must be a list")
        allowed_ids = {item.evidence_id for item in evidence}
        clean: list[dict[str, Any]] = []
        for index, item in enumerate(findings):
            if not isinstance(item, dict) or item.get("finding_type") not in _FINDING_TYPES:
                raise ModelOutputInvalid(f"fraud finding {index} has invalid classification")
            if item.get("party") not in {"rider", "driver", "both", "unknown"}:
                raise ModelOutputInvalid(f"fraud finding {index} has invalid party")
            summary = item.get("summary")
            source_fields = item.get("source_fields")
            evidence_ids = item.get("evidence_ids")
            if not isinstance(summary, str) or not summary.strip():
                raise ModelOutputInvalid(f"fraud finding {index} has empty summary")
            if not isinstance(source_fields, list) or any(not isinstance(x, str) for x in source_fields):
                raise ModelOutputInvalid(f"fraud finding {index} has invalid source fields")
            if any(field not in _SOURCE_FIELDS for field in source_fields):
                raise ModelOutputInvalid(f"fraud finding {index} cites an unknown source field")
            if not isinstance(evidence_ids, list) or any(
                not isinstance(x, str) or x not in allowed_ids for x in evidence_ids
            ):
                raise ModelOutputInvalid(f"fraud finding {index} cites unknown evidence")
            clean.append({
                "finding_type": item["finding_type"],
                "party": item["party"],
                "summary": summary.strip(),
                "source_fields": source_fields,
                "evidence_ids": evidence_ids,
            })
        return {
            "risk_score": float(score),
            "confidence": float(confidence),
            "findings": clean,
            "provider": completion.provider.to_api(),
        }


def _probability(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and 0.0 <= value <= 1.0
    )


def _fraud_relevant_profile(profile: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "disputes_last_30d", "disputes_total", "fraud_flag_count", "prior_classifications",
    )
    return {key: profile[key] for key in fields if profile.get(key) is not None}
