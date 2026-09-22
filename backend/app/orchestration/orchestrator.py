"""The dispute orchestrator.

The WORKFLOW is deterministic; the CONCLUSIONS are the model's. Sequence:

  1. assemble case facts + runtime evidence from the DB accessors,
  2. evaluate policy -> PolicyContext (rule ids + measurements only, I-1),
  3. run the two advocates independently (each restricted to its party's visible evidence),
  4. resolve verified-over-unverified precedence per factual question (I-7),
  5. run the Judge over both advocates + case context + measurements + policy text,
  6. quarantine any external info (I-8),
  7. apply escalation (RP-ESC-*, D-09/10/11, RP-SAFETY-001) to the Judge's ruling,
  8. assemble the CaseResult and persist model work.

A DatabaseUnavailable anywhere aborts with an error and NO ruling (contract §1).
"""

from __future__ import annotations

from typing import Any

from app.domain import DisputeCategory, PHASE_ZERO_CATEGORIES
from app.evidence.external import ExternalInfoSource
from app.evidence.models import Evidence
from app.evidence.precedence import EvidencePrecedence, FactualQuestion
from app.models.components import Advocate, Judge
from app.orchestration.escalation import (
    ImpactInputs,
    assess_fraud_risk,
    decide_escalation,
    human_review_summary,
)
from app.orchestration.facts import assemble_evidence_bundle, assemble_facts
from app.persistence.reader import DatabaseReader, DatabaseUnavailable
from app.policy import evaluator
from app.policy.loader import PolicyDocument
from app.providers.base import ModelProvider, ProviderUnavailable


class Orchestrator:
    def __init__(
        self,
        *,
        reader: DatabaseReader,
        provider: ModelProvider,
        policy: PolicyDocument,
        external: ExternalInfoSource,
        store,
        settings,
    ) -> None:
        self.reader = reader
        self.provider = provider
        self.policy = policy
        self.external = external
        self.store = store
        self.settings = settings

    def run_case(self, case) -> dict[str, Any]:
        category = case.category
        currency = self.settings.currency

        facts = assemble_facts(self.reader, case)  # may raise DatabaseUnavailable
        # Assemble the evidence bundle from ride_data reads + party submissions (§6). This is
        # what the advocates cite and the Judge references; an empty bundle escalates (RP-EV-003).
        evidence = assemble_evidence_bundle(self.reader, case)
        evidence_ids = [e.evidence_id for e in evidence]
        # Persist the bundle so GET /evidence/{id} resolves every id the ruling references.
        self.store.save_evidence_bundle(case.case_id, [e.to_api() for e in evidence])

        policy_ctx = evaluator.evaluate(category, facts, self.policy)
        thresholds = self._thresholds()

        rider = Advocate("rider", self.provider)
        driver = Advocate("driver", self.provider)
        rider_out = rider.argue(category=category, policy=policy_ctx, evidence=evidence,
                                case_id=case.case_id, currency=currency)
        driver_out = driver.argue(category=category, policy=policy_ctx, evidence=evidence,
                                  case_id=case.case_id, currency=currency)

        precedence_notes, insufficient = self._precedence(category, evidence, facts)

        # RP-EV-003: a confident ruling on absent deciding evidence must be IMPOSSIBLE. If the
        # bundle is empty, or the verified evidence for this category's deciding question is
        # missing, the case is insufficient — it escalates and cannot resolve confidently.
        verified_ids = [e.evidence_id for e in evidence
                        if e.verification.status.value == "verified"]
        if not verified_ids or not self._deciding_evidence_present(category, evidence):
            insufficient = True

        judge = Judge(self.provider)
        judge_out = judge.rule(
            category=category,
            policy=policy_ctx,
            rider_arg=rider_out,
            driver_arg=driver_out,
            case_facts=facts,
            evidence_ids=evidence_ids,
            thresholds=thresholds,
            precedence_notes=precedence_notes,
            currency=currency,
        )

        # When the case is insufficient, the ruling cannot stand as a confident auto-resolution:
        # cap confidence below the escalation threshold so RP-EV-003 escalation always fires.
        if insufficient:
            cap = self.settings.escalation_confidence_threshold - 0.01
            judge_out["confidence"] = round(min(float(judge_out.get("confidence", 0.0)), cap), 3)

        # evidence_references = the VERIFIED records the ruling actually relied on (the deciding
        # question for this category), not the whole bundle. Every id here resolves via
        # GET /evidence/{id} because the bundle is persisted above.
        relied_on = self._relied_on_evidence_ids(category, evidence)
        judge_out["evidence_references"] = relied_on or evidence_ids

        # I-8: quarantine external info; never merge into evidence.
        ext = self.external.fetch(category, policy_ctx.measurement_map())
        external_findings = [
            {
                "source_url": f.source_url,
                "retrieved_at": f.retrieved_at,
                "reliability": f.reliability,
                "evaluation": f.evaluation,
                "content": f.content,
            }
            for f in ext.findings
        ]

        # Advisory precedent (I-2, RP-PREC-001).
        try:
            archive = self.reader.search_archive(category, policy_ctx.measurement_map(), 3)
        except DatabaseUnavailable:
            raise
        precedent_refs = [a.archive_case_id for a in archive]

        # Fraud / impact.
        filed_party_profile = (
            facts.get("rider_profile") if case.filed_by == "rider" else facts.get("driver_profile")
        )
        fraud_risk = assess_fraud_risk(filed_party_profile)
        amount_cents = int(
            (judge_out.get("recommended_action", {}).get("amount", {}) or {}).get("amount_cents", 0)
        )
        disputed_component = self._disputed_component(category, facts)
        safety_signal = self._safety_signal(facts)

        impact = ImpactInputs(
            category=category,
            amount_cents=amount_cents,
            fraud_risk=fraud_risk,
            party_disputes_30d=int((filed_party_profile or {}).get("disputes_last_30d", 0) or 0),
            safety_signal=safety_signal,
        )
        esc = decide_escalation(
            ruling_type=judge_out.get("ruling_type", "no_action"),
            confidence=float(judge_out.get("confidence", 0.0)),
            recommended_amount_cents=amount_cents,
            disputed_fare_component_cents=disputed_component,
            impact=impact,
            confidence_threshold=self.settings.escalation_confidence_threshold,
            high_impact_amount_cents=self.settings.high_impact_amount_cents,
            goodwill_cap_cents=self.settings.goodwill_cap_cents,
            fraud_threshold=self.settings.fraud_risk_escalation_threshold,
            insufficient=insufficient,
        )

        summary = ""
        if esc.escalated:
            summary = human_review_summary(
                category=category,
                question=self._question(category),
                evidence_relied_on=judge_out.get("evidence_references", []),
                conflict_or_gap=(
                    "; ".join(precedence_notes)
                    if precedence_notes
                    else ("insufficient/contradictory evidence" if insufficient else "policy thresholds")
                ),
                rider_argument=rider_out["argument"],
                driver_argument=driver_out["argument"],
                reasons=esc.reasons,
            )

        synthetic = bool(rider_out["_synthetic"] or driver_out["_synthetic"] or judge_out["_synthetic"])
        status = "escalated" if esc.escalated else "resolved"

        judge_block = {
            "ruling_type": judge_out.get("ruling_type"),
            "recommended_action": judge_out.get("recommended_action", {}),
            "confidence": judge_out.get("confidence"),
            "reasoning": judge_out.get("reasoning", ""),
            "evidence_references": judge_out.get("evidence_references", []),
            "policy_references": judge_out.get("policy_references", []),
            "precedent_references": precedent_refs,
            "precedent_binding": False,  # RP-PREC-001: advisory only
            "measurements": judge_out.get("measurements", {}),
            "escalation": {
                "escalated": esc.escalated,
                "reasons": esc.reasons,
                "human_review_summary": summary,
            },
            "provider": judge_out["provider"],
        }

        result = {
            "case_id": case.case_id,
            "ride_id": case.ride_id,
            "category": category,
            "status": status,
            "synthetic": True,  # synthetic system, synthetic data
            "synthetic_reasoning": synthetic,  # I-6
            "policy_version": policy_ctx.policy_version,
            "created_at": case.filed_at or "",
            "case_facts": self._case_facts_view(facts),
            "advocates": {
                "rider": _advocate_api(rider_out),
                "driver": _advocate_api(driver_out),
            },
            "judge": judge_block,
            "external_findings": external_findings,
            "external_unavailable": ext.unavailable,
            "urgency": self._urgency(esc, fraud_risk, amount_cents),
            "case_history": [],
        }

        # Persist durable model work (D-05) through the backend's OWN persistence layer,
        # which owns and writes tribunal.model_work_* (write matrix §6). The read contract
        # has no write surface — the reader is never asked to persist (I-2).
        work_payload = {
            "case_id": case.case_id,
            "advocates": result["advocates"],
            "judge": judge_block,
            "policy_version": policy_ctx.policy_version,
        }
        self.store.persist_model_work(case.case_id, work_payload)
        return result

    # --- helpers -------------------------------------------------------------
    def _thresholds(self) -> dict[str, float]:
        t = dict(self.policy.threshold_map())
        t.setdefault("confidence_threshold", self.settings.escalation_confidence_threshold)
        return t

    def _relied_on_evidence_ids(self, category, evidence: list[Evidence]) -> list[str]:
        """The verified records whose factual question the ruling turns on."""
        questions = {"route_deviation": {"distance", "fare", "stops"},
                     "no_show": {"arrival", "contact", "fare"}}.get(category, set())
        out: list[str] = []
        for e in evidence:
            if e.verification.status.value != "verified":
                continue
            if e.payload.get("_question") in questions:
                out.append(e.evidence_id)
        return out

    def _deciding_evidence_present(self, category, evidence: list[Evidence]) -> bool:
        """Is the VERIFIED evidence needed to decide this category present? route_deviation
        needs a verified distance reading; no_show needs verified arrival (and ideally
        wait/contact). Absent → the case cannot be decided confidently (RP-EV-003)."""
        def verified_payload_has(key: str) -> bool:
            for e in evidence:
                if e.verification.status.value != "verified":
                    continue
                found, val = e.field_value(f"payload.{key}")
                if found and val is not None:
                    return True
            return False

        if category == "route_deviation":
            return verified_payload_has("actual_distance_km") and verified_payload_has("planned_distance_km")
        if category == "no_show":
            return verified_payload_has("min_distance_to_pickup_m")
        return bool(evidence)

    def _precedence(self, category, evidence: list[Evidence], facts) -> tuple[list[str], bool]:
        """Return (conflict notes, insufficient?). I-7 lives here: an unverified item that
        contradicts a verified reading on the same question is noted; it must not flip."""
        ep = EvidencePrecedence()
        notes: list[str] = []
        insufficient = False

        # Group evidence by the factual question each speaks to.
        questions = self._questions_for(category, evidence)
        for q in questions:
            contradicts = {
                e.evidence_id
                for e in q.speaking_evidence
                if e.payload.get("_contradicts_verified")
            }
            outcome = ep.resolve(q, contradicts=contradicts)
            if outcome.conflict:
                notes.append(q.key)
            if outcome.weak_only and not outcome.verified_present:
                insufficient = True
        # Malformed evidence present → uncertainty.
        if any(e.payload.get("_malformed") for e in evidence):
            insufficient = True
        return notes, insufficient

    def _questions_for(self, category, evidence: list[Evidence]) -> list[FactualQuestion]:
        # A question groups evidence by the salient field it addresses.
        buckets: dict[str, list[Evidence]] = {}
        for e in evidence:
            key = e.payload.get("_question") or e.class_.value
            buckets.setdefault(key, []).append(e)
        return [FactualQuestion(key=k, speaking_evidence=tuple(v)) for k, v in buckets.items()]

    def _disputed_component(self, category, facts) -> int:
        ride = facts.get("ride") or {}
        fare = facts.get("fare") or {}
        if category == "no_show":
            return int(fare.get("cancellation_fee_cents", 0) or 0)
        # route_deviation: the disputed component is the charged fare (cap for a refund).
        return int(ride.get("charged_fare_cents", 0) or 0)

    def _safety_signal(self, facts) -> bool:
        for msg in (facts.get("chat") or {}).get("messages", []) or []:
            if msg.get("kind") == "safety_flag" or msg.get("safety") is True:
                return True
        return False

    def _question(self, category) -> str:
        return {
            "route_deviation": "Was the fare overcharged due to an unjustified route deviation?",
            "no_show": "Was the cancellation fee validly charged?",
        }.get(category, "Adjudicate the dispute.")

    def _urgency(self, esc, fraud_risk: float, amount_cents: int) -> float:
        u = 0.3
        if esc.escalated:
            u += 0.3
        if esc.high_impact:
            u += 0.2
        u += min(fraud_risk, 0.2)
        return round(min(u, 1.0), 2)

    def _case_facts_view(self, facts) -> dict[str, Any]:
        """A denormalized ride summary with NO outcome fields (contract §3)."""
        ride = facts.get("ride") or {}
        route = facts.get("route") or {}
        return {
            "ride_id": ride.get("ride_id"),
            "status": ride.get("status"),
            "quoted_fare_cents": ride.get("quoted_fare_cents"),
            "charged_fare_cents": ride.get("charged_fare_cents"),
            "planned_distance_km": route.get("planned_distance_km"),
            "actual_distance_km": route.get("actual_distance_km"),
        }


def _advocate_api(out: dict[str, Any]) -> dict[str, Any]:
    return {
        "argument": out["argument"],
        "claims": out["claims"],
        "policy_references": out["policy_references"],
        "rejected_evidence": out["rejected_evidence"],
        "invalid_citation_count": out["invalid_citation_count"],
        "invalid_citation_rate": out["invalid_citation_rate"],
        "provider": out["provider"],
    }
