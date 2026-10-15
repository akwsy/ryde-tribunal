"""Audit advocates' claims against the case evidence before the Judge rules."""

from __future__ import annotations

from copy import deepcopy
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
        claims = {
            party: [claim for claim in data.get("claims", []) if isinstance(claim, dict)]
            for party, data in (("rider", rider), ("driver", driver))
        }
        claim_texts = sorted({
            claim["text"] for party_claims in claims.values() for claim in party_claims
            if isinstance(claim.get("text"), str)
        })
        allowed_ids = sorted(item.evidence_id for item in evidence)
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
                "Use unknown if you cannot determine whether it could affect the ruling. Copy claim_text "
                "verbatim from the supplied claims, and copy evidence references only from the "
                "supplied evidence IDs. Do not create paraphrased or combined claims."
            ),
            "category": category,
            "policy_rules": policy_rules,
            "advocates": {"rider": rider, "driver": driver},
            "evidence": [item.to_api() for item in evidence],
            "allowed_claim_texts": claim_texts,
            "allowed_evidence_ids": allowed_ids,
        }
        schema = deepcopy(_SCHEMA)
        finding_properties = schema["properties"]["findings"]["items"]["properties"]
        finding_properties["claim_text"]["enum"] = claim_texts
        finding_properties["evidence_references"]["items"]["enum"] = allowed_ids
        completion = self.provider.complete(prompt, schema)
        data = completion.data
        findings = data.get("findings") if isinstance(data, dict) else None
        if not isinstance(findings, list):
            raise ModelOutputInvalid("evidence audit findings must be a list")
        # Only source records in the assembled case bundle are valid evidence. A model
        # citation cannot make a missing or fabricated ID valid merely by mentioning it.
        allowed_ids = set(allowed_ids)
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
            unknown_references = [evidence_id for evidence_id in evidence_ids if evidence_id not in allowed_ids]
            if unknown_references:
                classification = "unsupported"
                materiality = "unknown"
                explanation = (
                    explanation.strip()
                    + " The auditor referenced a record that is not present in this case bundle."
                )
                evidence_ids = [evidence_id for evidence_id in evidence_ids if evidence_id in allowed_ids]
            finding = {
                "party": party,
                "claim_text": claim_text,
                "classification": classification,
                "confidence": float(confidence),
                "explanation": explanation.strip(),
                "evidence_references": evidence_ids,
                "materiality": materiality,
            }
            clean.append(finding)

        # Add a deterministic citation-integrity pass alongside the model's semantic
        # comparison. This catches omitted citations and invalid IDs even if the auditor
        # model overlooks them. These findings remain advisory; the Judge's safety gate
        # decides whether they require human review.
        existing_findings = {
            (item["party"], item["claim_text"], item["classification"])
            for item in clean
        }
        for party, party_data in (("rider", rider), ("driver", driver)):
            for claim in party_data.get("claims", []):
                if not isinstance(claim, dict) or not isinstance(claim.get("text"), str):
                    continue
                citations = claim.get("citations", [])
                invalid = [citation for citation in citations if
                    not isinstance(citation, dict) or citation.get("valid") is not True or
                    citation.get("evidence_id") not in allowed_ids]
                if not citations:
                    explanation = "This factual claim has no supporting evidence citation."
                elif invalid:
                    missing_ids = sorted({
                        citation.get("evidence_id", "unknown")
                        for citation in invalid if isinstance(citation, dict)
                        and citation.get("evidence_id") not in allowed_ids
                    })
                    explanation = (
                        "The cited record could not be verified in this case's evidence bundle"
                        + (f" ({', '.join(missing_ids)})." if missing_ids else ".")
                    )
                else:
                    continue
                key = (party, claim["text"], "unsupported")
                if key in existing_findings:
                    continue
                refs = sorted({
                    citation["evidence_id"] for citation in invalid
                    if isinstance(citation, dict) and citation.get("evidence_id") in allowed_ids
                })
                clean.append({
                    "party": party, "claim_text": claim["text"],
                    "classification": "unsupported", "confidence": 1.0,
                    "explanation": explanation, "evidence_references": refs,
                    "materiality": "unknown",
                })
                existing_findings.add(key)
        return {"findings": clean, "provider": completion.provider.to_api()}
