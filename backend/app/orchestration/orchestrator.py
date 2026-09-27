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

from datetime import datetime, timezone
from typing import Any

from app.domain import DisputeCategory
from app.evidence.external import ExternalInfoSource
from app.evidence.models import Evidence
from app.evidence.precedence import EvidencePrecedence, FactualQuestion
from app.models.components import Advocate, Judge
from app.models.evidence_auditor import EvidenceAuditor
from app.models.fraud_detector import FraudDetector
from app.models.judging_config import JudgingConfig, load_judging_config
from app.orchestration.escalation import (
    ImpactInputs,
    assert_ruling_integrity,
    decide_escalation,
    finalize_ruling,
    human_review_summary,
)
from app.orchestration.facts import assemble_evidence_bundle, assemble_facts
from app.persistence.reader import DatabaseReader, DatabaseUnavailable
from app.policy import evaluator
from app.policy.loader import PolicyDocument
from app.providers.base import ModelOutputInvalid, ModelProvider, ProviderUnavailable
from app.providers.deterministic_mock import DeterministicMockProvider


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
        fallback_provider: ModelProvider | None = None,
    ) -> None:
        self.reader = reader
        self.provider = provider
        self.policy = policy
        self.external = external
        self.store = store
        self.settings = settings
        self.judging_config: JudgingConfig = load_judging_config(
            getattr(settings, "judging_config_path", "") or None
        )
        # The fallback is deliberately a separate provider instance. A request that starts
        # with an LLM must restart its complete model pass on this provider if any component
        # call fails; outputs from a partial LLM pass are never mixed into a ruling.
        self.fallback_provider = fallback_provider or DeterministicMockProvider(
            model="ryde-mock-judge-1"
        )

    def run_case(
        self, case, *, _provider: ModelProvider | None = None, _fallback_attempted: bool = False
    ) -> dict[str, Any]:
        provider = _provider or self.provider
        category = case.category
        currency = self.settings.currency

        facts = assemble_facts(self.reader, case)  # may raise DatabaseUnavailable
        # Assemble the evidence bundle from ride_data reads + party submissions (§6). This is
        # what the advocates cite and the Judge references; an empty bundle escalates (RP-EV-003).
        evidence = assemble_evidence_bundle(
            self.reader,
            case,
            allocate_evidence_id=self.store.allocate_evidence_id,
            facts=facts,
        )
        evidence_ids = [e.evidence_id for e in evidence]
        # Persist the bundle so GET /evidence/{id} resolves every id the ruling references.
        self.store.save_evidence_bundle(case.case_id, [e.to_api() for e in evidence])

        policy_ctx = evaluator.evaluate(category, facts, self.policy)
        thresholds = self._thresholds()
        filed_party_profile = (
            facts.get("rider_profile") if case.filed_by == "rider" else facts.get("driver_profile")
        )
        # Historical results are fetched before model execution so the Judge can inspect
        # origin and credibility. Archive access is read-only and failures must not trigger
        # LLM fallback; they remain database errors.
        archive = self.reader.search_archive(category, policy_ctx.measurement_map(), 3)
        precedent_refs = [a.archive_case_id for a in archive]
        reference_time = _parse_timestamp(getattr(case, "filed_at", ""))
        precedent_context = []
        for a in archive:
            historical_rulings = a.rulings or [{
                "stage": "reviewer_approved" if a.decision_origin == "human" else "model_proposed",
                "ruling_type": a.ruling_type,
                "recommended_action": a.recommended_action,
                "confidence": a.confidence,
                "decision_origin": a.decision_origin,
            }]
            for ruling in historical_rulings:
                origin = ruling.get("decision_origin", "agent")
                origin_weight = (
                    self.judging_config.human_approved_weight
                    if origin == "human"
                    else self.judging_config.model_proposed_weight
                )
                decided_at = ruling.get("decided_at") or _first_timestamp(
                    a, "decided_at", "decision_at", "created_at", "filed_at"
                )
                recency = _recency_weight(reference_time, decided_at,
                                          self.judging_config.recency_half_life_days)
                precedent_context.append({
                    "archive_case_id": a.archive_case_id,
                    "ruling_stage": ruling.get("stage"),
                    "ruling_type": ruling.get("ruling_type"),
                    "recommended_action": ruling.get("recommended_action"),
                    "confidence": ruling.get("confidence", a.confidence),
                    "decision_origin": origin,
                    "credibility": "higher" if origin == "human" else "standard",
                    "was_overridden": a.was_overridden,
                    "policy_version": a.policy_version,
                    "decided_at": decided_at,
                    "recency_weight": recency,
                    "effective_precedent_weight": round(origin_weight * recency, 6),
                })
        # Also expose previous tribunal cases as advisory examples. Keep the proposed and
        # reviewer-approved versions separate so the Judge can see who authored each one.
        prior_cases = [
            r for r in self.store.list_case_results()
            if r.get("case_id") != case.case_id and r.get("category") == category
            and (r.get("model_proposed_ruling") or r.get("judge"))
        ][-3:]
        for prior in prior_cases:
            proposed = prior.get("model_proposed_ruling")
            if proposed is None and prior.get("judge"):
                old_judge = prior["judge"]
                proposed = {
                    "ruling_type": old_judge.get("ruling_type"),
                    "recommended_action": old_judge.get("recommended_action", {}),
                    "author_type": "model",
                    "author_id": old_judge.get("provider", {}).get("model", ""),
                }
            if proposed:
                decided_at = prior.get("reviewed_at") or prior.get("created_at")
                recency = _recency_weight(reference_time, decided_at,
                                          self.judging_config.recency_half_life_days)
                precedent_context.append({
                    "case_id": prior["case_id"],
                    "source": "prior_tribunal_case",
                    "ruling_type": proposed.get("ruling_type"),
                    "recommended_action": proposed.get("recommended_action", {}),
                    "decision_origin": "agent",
                    "credibility": "standard",
                    "was_overridden": prior.get("status") == "overridden",
                    "decided_at": decided_at,
                    "recency_weight": recency,
                    "effective_precedent_weight": round(
                        self.judging_config.model_proposed_weight * recency, 6
                    ),
                })
            approved = prior.get("reviewer_approved_ruling")
            if approved:
                decided_at = prior.get("reviewed_at") or prior.get("created_at")
                recency = _recency_weight(reference_time, decided_at,
                                          self.judging_config.recency_half_life_days)
                precedent_context.append({
                    "case_id": prior["case_id"],
                    "source": "prior_tribunal_case",
                    "ruling_type": approved.get("ruling_type"),
                    "recommended_action": approved.get("recommended_action", {}),
                    "decision_origin": "human",
                    "credibility": "higher",
                    "was_overridden": False,
                    "decided_at": decided_at,
                    "recency_weight": recency,
                    "effective_precedent_weight": round(
                        self.judging_config.human_approved_weight * recency, 6
                    ),
                })

        rider = Advocate("rider", provider)
        driver = Advocate("driver", provider)

        # Provider errors are caught only around model calls. Database errors, archive
        # access failures and all other infrastructure errors retain their own semantics.
        try:
            rider_out = rider.argue(category=category, policy=policy_ctx, evidence=evidence,
                                    case_id=case.case_id, currency=currency)
            driver_out = driver.argue(category=category, policy=policy_ctx, evidence=evidence,
                                      case_id=case.case_id, currency=currency)

            precedence_notes, insufficient = self._precedence(category, evidence, facts)

            audit = EvidenceAuditor(provider).audit(
                rider=rider_out, driver=driver_out, evidence=evidence,
                category=category,
                policy_rules=[
                    {"rule_id": rule.rule_id, "text": rule.text}
                    for rule in policy_ctx.applicable_rules
                ],
            )
            audit_findings = audit["findings"]
            fraud_assessment = FraudDetector(provider).assess(
                party=case.filed_by,
                profile=filed_party_profile,
                evidence=evidence,
                evidence_audit=audit_findings,
                advocate_claims={"rider": rider_out, "driver": driver_out},
            )
            fraud_assessment = {
                **fraud_assessment,
                "influence_weight": self.judging_config.fraud_influence_weight,
                "assessment_note": self.judging_config.fraud_assessment_note,
            }
            fraud_risk = fraud_assessment["risk_score"]

            verified_ids = [e.evidence_id for e in evidence
                            if e.verification.status.value == "verified"]
            if not verified_ids or not self._deciding_evidence_present(category, evidence):
                insufficient = True

            contradiction_note = self._fare_contradiction(category, case, facts)

            judge = Judge(provider)
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
                extra_measurements={
                    "filing_asserts_fee": bool(contradiction_note),
                    "evidence_insufficient": insufficient,
                },
                precedents=precedent_context,
                evidence_audit=audit_findings,
                fraud_assessment=fraud_assessment,
                judging_weights={
                    "policy_priority": self.judging_config.policy_priority,
                    "human_approved_weight": self.judging_config.human_approved_weight,
                    "model_proposed_weight": self.judging_config.model_proposed_weight,
                    "recency_half_life_days": self.judging_config.recency_half_life_days,
                    "fraud_influence_weight": self.judging_config.fraud_influence_weight,
                    "fraud_assessment_note": self.judging_config.fraud_assessment_note,
                },
            )
        except (ProviderUnavailable, ModelOutputInvalid):
            if provider.meta.kind != "llm" or _fallback_attempted:
                raise
            # Re-enter the full case path with the deterministic provider. Any completed
            # LLM advocate output above is discarded; database failures during this retry
            # are intentionally not caught here and remain database_unavailable.
            return self.run_case(
                case, _provider=self.fallback_provider, _fallback_attempted=True
            )

        # Point 1 — structural: a refund/compensation MUST carry a positive amount. A figureless
        # monetary remedy is downgraded to no_action here (all categories), and the case becomes
        # insufficient so it escalates rather than emitting a remedy with no figure.
        judge_out, downgraded = finalize_ruling(judge_out)
        if downgraded:
            insufficient = True
        if contradiction_note:
            insufficient = True
            precedence_notes = list(precedence_notes) + [contradiction_note]

        if audit_findings:
            audit_text = "; ".join(
                f"{f['classification']} ({f['party']} claim: {f['claim_text']}): {f['explanation']}"
                for f in audit_findings
            )
            judge_out["reasoning"] = (
                f"{judge_out.get('reasoning', '')} Evidence audit findings considered: {audit_text}."
            ).strip()
        fraud_findings = fraud_assessment.get("findings", [])
        if fraud_findings:
            fraud_text = "; ".join(f["summary"] for f in fraud_findings)
            judge_out["reasoning"] = (
                f"{judge_out.get('reasoning', '')} Fraud-risk assessment "
                f"({fraud_assessment['risk_score']:.3f}, confidence "
                f"{fraud_assessment['confidence']:.3f}) was weighed as credibility context, not "
                f"proof: {fraud_text}."
            ).strip()

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
        if category == "safety_incident":
            # For safety rulings, expose only the evidence the Judge tied to each decisive fact.
            # The gate below confirms every such reference resolves to a verified bundle item.
            decisive_refs = sorted({
                reference
                for fact in judge_out.get("decisive_facts", [])
                for reference in fact.get("evidence_references", [])
            })
            judge_out["evidence_references"] = decisive_refs
            judge_out["safety_auto_ruling_eligible"] = self._safety_auto_ruling_eligible(
                judge_out=judge_out,
                evidence=evidence,
                audit_findings=audit_findings,
                precedence_notes=precedence_notes,
                contradiction_note=contradiction_note,
                insufficient=insufficient,
                confidence_threshold=self.settings.escalation_confidence_threshold,
            )

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

        # Fraud / impact.
        amount_cents = int(
            (judge_out.get("recommended_action", {}).get("amount", {}) or {}).get("amount_cents", 0)
        )
        disputed_component = self._disputed_component(category, facts)
        safety_signal = self._safety_signal(facts)

        impact = ImpactInputs(
            category=category,
            amount_cents=amount_cents,
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
            insufficient=insufficient,
            safety_auto_eligible=bool(judge_out.get("safety_auto_ruling_eligible", False)),
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
                evidence_shows=self._evidence_shows(evidence),
                evidence_does_not_show=self._evidence_gaps(category, facts, evidence),
                audit_findings=audit_findings,
                fraud_assessment=fraud_assessment,
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
            "decisive_facts": judge_out.get("decisive_facts", []),
            "escalation": {
                "escalated": esc.escalated,
                "reasons": esc.reasons,
                "human_review_summary": summary,
            },
            "provider": judge_out["provider"],
        }
        # Last-line invariant: a refund/compensation in the returned payload MUST carry a
        # positive amount. finalize_ruling above already downgrades a figureless remedy, so this
        # only fires on a logic error — and then it fails loud rather than emitting a bad ruling.
        assert_ruling_integrity(judge_block)

        result = {
            "case_id": case.case_id,
            "ride_id": case.ride_id,
            "category": category,
            "status": status,
            # Source provenance is metadata only; imported company and generated records
            # pass through the identical retrieval and adjudication path.
            "synthetic": bool(facts.get("ride", {}).get("synthetic", True)),
            "synthetic_reasoning": synthetic,  # I-6
            "policy_version": policy_ctx.policy_version,
            "created_at": case.filed_at or "",
            "case_facts": self._case_facts_view(facts),
            "evidence_audit": audit,
            "fraud_assessment": fraud_assessment,
            "advocates": {
                "rider": _advocate_api(rider_out),
                "driver": _advocate_api(driver_out),
            },
            "judge": judge_block,
            "model_proposed_ruling": {
                "ruling_type": judge_block["ruling_type"],
                "recommended_action": judge_block["recommended_action"],
                "author_type": "model",
                "decision_origin": "agent",
                "author_id": judge_block["provider"]["model"],
                "credibility": "model_proposed",
            },
            "reviewer_approved_ruling": None,
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
        t.setdefault("goodwill_cap_cents", self.settings.goodwill_cap_cents)
        return t

    def _fare_contradiction(self, category, case, facts) -> str | None:
        """A material contradiction between the FILING and the verified fare record: the filing
        asserts a charge the record does not show. Returns a human-readable note or None.

        - no_show_charge: the filing disputes a cancellation fee, but the verified fare record shows
          `cancellation_fee_cents == 0` — no fee was ever charged.
        - route_deviation: the filing claims an overcharge, but the verified record shows the
          rider was charged no more than quoted (`charged <= quoted`).
        Only flagged when the filing actually asserts the charge (a no_show_charge filing inherently
        disputes a fee; a claimed_amount, if present, is corroborating)."""
        ride = facts.get("ride") or {}
        fare = facts.get("fare") or {}
        if category == "no_show_charge":
            fee = int(fare.get("cancellation_fee_cents", ride.get("charged_fare_cents", 0)) or 0)
            if fee == 0:
                return ("filing disputes a cancellation fee, but the verified fare record shows "
                        "no fee was charged (cancellation_fee_cents=0)")
        if category == "route_deviation":
            claimed = getattr(case, "claimed_amount_cents", None)
            charged = int(ride.get("charged_fare_cents", 0) or 0)
            quoted = int(ride.get("quoted_fare_cents", 0) or 0)
            if claimed and charged <= quoted:
                return ("filing claims an overcharge, but the verified fare record shows "
                        f"charged {charged}c <= quoted {quoted}c (no overcharge)")
        return None

    def _relied_on_evidence_ids(self, category, evidence: list[Evidence]) -> list[str]:
        """The verified records whose factual question the ruling turns on."""
        questions = {"route_deviation": {"distance", "fare", "stops"},
                     "no_show_charge": {"arrival", "contact", "fare"}}.get(category, set())
        out: list[str] = []
        for e in evidence:
            if e.verification.status.value != "verified":
                continue
            if e.payload.get("_question") in questions:
                out.append(e.evidence_id)
        return out

    def _deciding_evidence_present(self, category, evidence: list[Evidence]) -> bool:
        """Is the VERIFIED evidence needed to decide this category present? route_deviation
        needs a verified distance reading; no_show_charge needs verified arrival (and ideally
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
        if category == "no_show_charge":
            return verified_payload_has("min_distance_to_pickup_m")
        return bool(evidence)

    def _safety_auto_ruling_eligible(
        self,
        *,
        judge_out: dict[str, Any],
        evidence: list[Evidence],
        audit_findings: list[dict[str, Any]],
        precedence_notes: list[str],
        contradiction_note: str | None,
        insufficient: bool,
        confidence_threshold: float,
    ) -> bool:
        """Fail closed unless every owner-approved safety auto-ruling condition is explicit."""
        if insufficient or precedence_notes or contradiction_note:
            return False
        confidence = judge_out.get("confidence")
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or confidence < confidence_threshold):
            return False

        evidence_by_id: dict[str, Evidence] = {}
        for item in evidence:
            if item.evidence_id in evidence_by_id:
                return False
            evidence_by_id[item.evidence_id] = item
        decisive_facts = judge_out.get("decisive_facts")
        if not isinstance(decisive_facts, list) or not decisive_facts:
            return False
        for fact in decisive_facts:
            if not isinstance(fact, dict) or not isinstance(fact.get("fact"), str):
                return False
            references = fact.get("evidence_references")
            if not isinstance(references, list) or not references:
                return False
            for reference in references:
                item = evidence_by_id.get(reference) if isinstance(reference, str) else None
                if item is None or item.verification.status.value != "verified":
                    return False

        if not isinstance(audit_findings, list):
            return False
        material_flags = {"contradicted", "incorrect", "fabrication_suspected"}
        for finding in audit_findings:
            if not isinstance(finding, dict):
                return False
            classification = finding.get("classification")
            if classification not in {
                "contradicted", "incorrect", "fabrication_suspected", "unsupported",
                "consistent", "inconclusive",
            }:
                return False
            if classification in material_flags:
                # Unknown/missing materiality is not clearance.
                if finding.get("materiality") != "non_material":
                    return False
        return True

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
        if category == "no_show_charge":
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
            "no_show_charge": "Was the cancellation fee validly charged?",
        }.get(category, "Adjudicate the dispute.")

    def _evidence_shows(self, evidence: list[Evidence]) -> list[str]:
        """Describe established, verified readings without converting claims into facts."""
        shown: list[str] = []
        for item in evidence:
            if item.verification.status.value != "verified":
                continue
            field, value = _salient_value(item)
            if field is not None:
                shown.append(f"{item.evidence_id} ({field}={value!r})")
            else:
                shown.append(f"{item.evidence_id} ({item.class_.value}; no summary field)")
        return shown

    def _evidence_gaps(self, category, facts, evidence: list[Evidence]) -> list[str]:
        gaps: list[str] = []
        keys = {
            "route_deviation": ("actual_distance_km", "planned_distance_km"),
            "no_show_charge": ("min_distance_to_pickup_m",),
        }.get(category, ())
        for key in keys:
            if not _verified_field_present(evidence, key):
                gaps.append(f"No verified evidence establishes {key}.")
        for item in evidence:
            if item.verification.status.value != "verified":
                field, value = _salient_value(item)
                detail = f" {field}={value!r}" if field is not None else ""
                gaps.append(
                    f"{item.evidence_id}{detail} is {item.verification.status.value} and does not establish a verified fact."
                )
        return gaps

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


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _first_timestamp(record, *keys: str) -> str | None:
    for key in keys:
        value = getattr(record, key, None)
        if isinstance(value, str) and value.strip() and _parse_timestamp(value):
            return value
    return None


def _recency_weight(reference: datetime | None, precedent_at: Any, half_life_days: float) -> float:
    precedent = _parse_timestamp(precedent_at)
    if reference is None or precedent is None:
        # Legacy archive rows without a decision timestamp retain origin credibility, but
        # are explicitly marked as lacking recency evidence in the Judge prompt.
        return 1.0
    age_days = max(0.0, (reference - precedent).total_seconds() / 86400)
    return 0.5 ** (age_days / half_life_days)


def _salient_value(item: Evidence) -> tuple[str | None, Any]:
    for key in (
        "actual_distance_km", "planned_distance_km", "deviation_pct",
        "min_distance_to_pickup_m", "driver_waited_seconds", "contact_attempt_recorded",
        "cancellation_fee_cents", "event_type", "details", "status", "text",
    ):
        found, value = item.field_value(f"payload.{key}")
        if found:
            return key, value
    return None, None


def _verified_field_present(evidence: list[Evidence], key: str) -> bool:
    return any(
        item.verification.status.value == "verified"
        and item.field_value(f"payload.{key}")[0]
        and item.field_value(f"payload.{key}")[1] is not None
        for item in evidence
    )
