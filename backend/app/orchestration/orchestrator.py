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

import re
from datetime import datetime, timezone
from typing import Any

from app.domain import DisputeCategory
from app.evidence.external import ExternalInfoSource
from app.evidence.models import Evidence
from app.evidence.precedence import EvidencePrecedence, FactualQuestion
from app.models.components import Judge
from app.models.evidence_tools import event
from app.orchestration.official_gate import (
    explain_gap_source_check,
    model_review_blockers,
    model_review_reason_codes,
    review_gaps,
    validate_final_output,
)
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
        self, case, *, _provider: ModelProvider | None = None, _fallback_attempted: bool = False,
        _trace: list | None = None, _force_human_review_reason: str | None = None,
    ) -> dict[str, Any]:
        provider = _provider or self.provider
        trace = list(_trace or [])
        from app.policy.loader import is_source_backed_policy
        official = is_source_backed_policy(self.policy.version)
        dispute = {"subject":case.subject, "description":case.description, "filed_by":case.filed_by,
                   "filed_at":case.filed_at, "category":case.category,
                   "category_details":getattr(case, "category_details", {})}
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

        trace.append(event("system", "evidence_assembled", "Retrieved and persisted source evidence snapshot", evidence_ids))
        if official:
            facts["filing"] = {"filed_at":case.filed_at,
                                "category_details": getattr(case, "category_details", {})}
        policy_ctx = evaluator.evaluate(category, facts, self.policy)
        thresholds = self._thresholds()
        filed_party_profile = (
            facts.get("rider_profile") if case.filed_by == "rider" else facts.get("driver_profile")
        )
        # Historical results are fetched before model execution so the Judge can inspect
        # origin and credibility. Archive access is read-only and failures must not trigger
        # LLM fallback; they remain database errors.
        archive = self.reader.search_archive(category, policy_ctx.measurement_map(), 3)
        if official:
            archive = [a for a in archive if getattr(a, "policy_version", None) == self.policy.version]
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

        # The deterministic first pass is deliberately narrow: when source-backed policy
        # and verified facts prove a unique outcome, it resolves without any provider call.
        from app.orchestration.rules_first import clear_ruling, rule_advocate, verify_rule_advocates
        judge_out = clear_ruling(category, facts, evidence, case.filed_at, policy_ctx) if official else None
        rules_rider = rule_advocate("rider", evidence, policy_ctx.rule_ids(), category=category,
                                    facts=facts, policy_version=policy_ctx.policy_version) if judge_out else None
        rules_driver = rule_advocate("driver", evidence, policy_ctx.rule_ids(), category=category,
                                     facts=facts, policy_version=policy_ctx.policy_version) if judge_out else None
        rules_precedence_notes, rules_insufficient = (
            self._precedence(category, evidence, facts) if judge_out else ([], False)
        )
        rules_audit_findings = (
            verify_rule_advocates(rules_rider, rules_driver, evidence) if judge_out else []
        )
        if judge_out and (rules_insufficient or rules_precedence_notes
                          or rules_audit_findings
                          or self._safety_signal(facts)
                          or int((filed_party_profile or {}).get("fraud_flag_count", 0) or 0) > 0
                          or float(judge_out.get("confidence", 0.0)) < self.settings.escalation_confidence_threshold
                          or not self._deciding_evidence_present(category, evidence, (getattr(case, "category_details", {}) or {}).get("fee_type"))
                          or self._fare_contradiction(category, case, facts)):
            judge_out = None
        if judge_out and review_gaps(category, facts, case.filed_at, judge_out, [], [rules_rider, rules_driver],
                                     official_policy=official):
            judge_out = None
        if judge_out is not None:
            rider_out = rules_rider
            driver_out = rules_driver
            trace.append(event("rider_advocate", "argument_completed", rider_out["argument"], rider_out["_cited_evidence_ids"], "ryde-policy-rules-1"))
            trace.append(event("driver_advocate", "argument_completed", driver_out["argument"], driver_out["_cited_evidence_ids"], "ryde-policy-rules-1"))
            audit_findings = rules_audit_findings
            rules_provider = {"kind": "rules-engine", "model": "ryde-policy-rules-1",
                              "display_name": "rules-based review", "policy_version": policy_ctx.policy_version}
            audit = {"findings": audit_findings, "provider": rules_provider}
            fraud_assessment = {
                "risk_score": 0.0, "confidence": 1.0, "findings": [],
                "provider": rules_provider,
                "influence_weight": self.judging_config.fraud_influence_weight,
                "assessment_note": self.judging_config.fraud_assessment_note,
            }
            fraud_risk = 0.0
            precedence_notes, insufficient = rules_precedence_notes, rules_insufficient
            trace.append(event("evidence_auditor", "audit_completed", "Citation integrity and source verification passed; no unsupported advocate claims were used", provider="rules-engine"))
            trace.append(event("fraud_detector", "risk_screen_completed", "No safety signal or explicit fraud flag was found; profile history alone was not treated as fault", provider="rules-engine"))
            trace.append(event("judge", "rules_first_review", "Verified facts satisfy a clear published-policy outcome; Gemini was not called", judge_out["evidence_references"], "ryde-policy-rules-1"))
            trace.append(event("judge", "ruling_proposed", judge_out["reasoning"], judge_out["evidence_references"], "ryde-policy-rules-1"))
        else:
            # All read-only sources have already been assembled once above. Do one targeted
            # gap check against that fixed snapshot; repeat advocate summaries cannot add
            # evidence and used to create three indistinguishable repair rounds.
            preliminary = {
                "ruling_type": "no_action", "recommended_action": {"delivery": "none"},
                "confidence": 0.0, "decisive_facts": [], "policy_references": [],
            }
            last_gaps = review_gaps(category, facts, case.filed_at, preliminary, [], [],
                                    official_policy=official)
            if not last_gaps:
                last_gaps = ["The policy outcome is not covered by a clear first-pass rule."]
            initial_rider = rule_advocate("rider", evidence, policy_ctx.rule_ids(), category=category,
                                          facts=facts, policy_version=policy_ctx.policy_version)
            initial_driver = rule_advocate("driver", evidence, policy_ctx.rule_ids(), category=category,
                                           facts=facts, policy_version=policy_ctx.policy_version)
            trace.append(event("rider_advocate", "argument_completed", initial_rider["argument"], initial_rider["_cited_evidence_ids"], "ryde-policy-rules-1"))
            trace.append(event("driver_advocate", "argument_completed", initial_driver["argument"], initial_driver["_cited_evidence_ids"], "ryde-policy-rules-1"))
            initial_findings = verify_rule_advocates(initial_rider, initial_driver, evidence)
            trace.append(event("evidence_auditor", "audit_completed",
                               f"{len(initial_findings)} citation integrity issue(s) found in the initial submissions",
                               provider="rules-engine"))
            trace.append(event("judge", "initial_review", "; ".join(last_gaps)))
            repair_resolved = False
            repair_profile_flags = int((filed_party_profile or {}).get("fraud_flag_count", 0) or 0)
            max_repair_rounds = 1 if official else 3
            for repair_round in range(1, max_repair_rounds + 1 if not _fallback_attempted else 1):
                trace.append(event("judge", "review_round",
                                   f"Checking unresolved evidence and policy gaps, round {repair_round} of {max_repair_rounds}"))
                trace.append(event("judge", "advocate_repair_requested", "; ".join(last_gaps)))
                for gap in last_gaps:
                    summary, checked_ids = explain_gap_source_check(gap, facts, evidence)
                    trace.append(event("judge", "evidence_gap_check", summary, checked_ids,
                                       "rules-engine"))
                rider_repair = rule_advocate("rider", evidence, policy_ctx.rule_ids(), last_gaps,
                                             category=category, facts=facts,
                                             policy_version=policy_ctx.policy_version)
                driver_repair = rule_advocate("driver", evidence, policy_ctx.rule_ids(), last_gaps,
                                              category=category, facts=facts,
                                              policy_version=policy_ctx.policy_version)
                trace.append(event("rider_advocate", "repair_completed", rider_repair["argument"], rider_repair["_cited_evidence_ids"], "ryde-policy-rules-1"))
                trace.append(event("driver_advocate", "repair_completed", driver_repair["argument"], driver_repair["_cited_evidence_ids"], "ryde-policy-rules-1"))
                repair_findings = verify_rule_advocates(rider_repair, driver_repair, evidence)
                trace.append(event("evidence_verification", "verification_completed",
                                   (f"{len(repair_findings)} citation integrity issue(s) found"
                                    if repair_findings else "Source verification and citation integrity passed"),
                                   [item.evidence_id for item in evidence if item.verification.status.value != "verified"]))
                if repair_findings:
                    last_gaps = [f"{item['party'].title()} claim needs corrected evidence citation: {item['reason']}"
                                 for item in repair_findings]
                else:
                    # Re-run the same conservative policy gate against the repaired
                    # submissions. A repaired case may stop here; unresolved facts,
                    # conflicts, or unsupported remedies continue through all rounds.
                    repaired_candidate = clear_ruling(category, facts, evidence, case.filed_at, policy_ctx)
                    candidate_precedence, candidate_insufficient = self._precedence(category, evidence, facts)
                    candidate_gaps = (review_gaps(category, facts, case.filed_at, repaired_candidate,
                                                  [], [rider_repair, driver_repair], official_policy=official)
                                      if repaired_candidate else review_gaps(
                                          category, facts, case.filed_at, preliminary, [],
                                          [rider_repair, driver_repair], official_policy=official
                                      ))
                    if not repaired_candidate and not candidate_gaps:
                        candidate_gaps = ["No clear source-backed outcome after the targeted check."]
                    if repaired_candidate:
                        if candidate_insufficient:
                            candidate_gaps.append("Verified evidence precedence is insufficient or conflicting.")
                        if candidate_precedence:
                            candidate_gaps.extend(candidate_precedence)
                        if self._safety_signal(facts):
                            candidate_gaps.append("A safety signal requires human review.")
                        if repair_profile_flags > 0:
                            candidate_gaps.append("An explicit profile risk flag requires human review.")
                        if float(repaired_candidate.get("confidence", 0.0)) < self.settings.escalation_confidence_threshold:
                            candidate_gaps.append("Rules-first confidence is below the automatic-decision threshold.")
                        if not self._deciding_evidence_present(category, evidence, (getattr(case, "category_details", {}) or {}).get("fee_type")):
                            candidate_gaps.append("Decisive verified evidence is missing.")
                        contradiction = self._fare_contradiction(category, case, facts)
                        if contradiction:
                            candidate_gaps.append(contradiction)
                    if repaired_candidate and not candidate_gaps:
                        candidate_gaps.extend(validate_final_output(
                            category, facts, case.filed_at, repaired_candidate, [],
                            [rider_repair, driver_repair], evidence, policy_ctx,
                        ))
                    if repaired_candidate and not candidate_gaps:
                        judge_out = repaired_candidate
                        repair_resolved = True
                        trace.append(event("judge", "repair_satisfied",
                                           f"Verified evidence and policy now support a clear outcome after round {repair_round}; Gemini was not called",
                                           judge_out["evidence_references"], "ryde-policy-rules-1"))
                        rider_repair_final, driver_repair_final = rider_repair, driver_repair
                        repair_findings = []
                        break
                    last_gaps = candidate_gaps or last_gaps
            model_skip_reasons = []
            if official and not repair_resolved and not _fallback_attempted:
                current_precedence, current_insufficient = self._precedence(category, evidence, facts)
                model_skip_reasons = model_review_blockers(
                    last_gaps,
                    precedence_notes=current_precedence,
                    insufficient=current_insufficient,
                    decisive_evidence_present=self._deciding_evidence_present(category, evidence, (getattr(case, "category_details", {}) or {}).get("fee_type")),
                    contradiction_note=self._fare_contradiction(category, case, facts),
                    safety_signal=self._safety_signal(facts),
                    profile_flags=repair_profile_flags,
                )
            if model_skip_reasons:
                trace.append(event("judge", "human_review_without_model",
                                   "No Gemini call: the remaining issue requires source correction, policy clarification, or human judgment. "
                                   + "; ".join(model_skip_reasons), provider="rules-engine",
                                   reason_codes=model_review_reason_codes(model_skip_reasons)))
            elif not _fallback_attempted and not repair_resolved:
                if provider.meta.kind == "llm":
                    trace.append(event("judge", "gemini_escalation", "The Judge remains uncertain after a targeted source check; requesting one Gemini review", provider=provider.meta.display_name))
                else:
                    trace.append(event("judge", "model_escalation", "The Judge remains uncertain after a targeted source check; using the configured offline model", provider=provider.meta.display_name))
            rider_out = (rider_repair_final if repair_resolved else
                         rider_repair if not _fallback_attempted else initial_rider)
            driver_out = (driver_repair_final if repair_resolved else
                          driver_repair if not _fallback_attempted else initial_driver)
            audit_findings = repair_findings if not _fallback_attempted else initial_findings
            rules_provider = {"kind": "rules-engine", "model": "ryde-policy-rules-1",
                              "display_name": "rules-based review", "policy_version": policy_ctx.policy_version}
            audit = {"findings": audit_findings, "provider": rules_provider}
            trace.append(event("evidence_auditor", "audit_completed",
                               f"{len(audit_findings)} evidence finding(s) passed to the Judge",
                               provider="rules-engine"))
            profile_flags = int((filed_party_profile or {}).get("fraud_flag_count", 0) or 0)
            dispute_history = int((filed_party_profile or {}).get("disputes_last_30d", 0) or 0)
            fraud_findings = ([{
                "finding_type": "potentially_fabricated_reference", "party": case.filed_by,
                "summary": "The source profile contains an explicit fraud flag; this is a review signal, not proof.",
                "source_fields": ["profile_history.fraud_flag_count"], "evidence_ids": [],
            }] if profile_flags > 0 else ([{
                "finding_type": "prior_dispute_density", "party": case.filed_by,
                "summary": f"The profile records {dispute_history} recent disputes; this is weak context and not evidence of fault.",
                "source_fields": ["profile_history.disputes_last_30d"], "evidence_ids": [],
            }] if dispute_history > 0 else []))
            fraud_assessment = {
                "risk_score": 0.5 if profile_flags else (0.1 if dispute_history > 0 else 0.0),
                "confidence": 1.0 if profile_flags else (0.5 if dispute_history > 0 else 0.5),
                "findings": fraud_findings,
                "provider": rules_provider,
                "influence_weight": self.judging_config.fraud_influence_weight,
                "assessment_note": self.judging_config.fraud_assessment_note,
            }
            fraud_risk = fraud_assessment["risk_score"]
            trace.append(event("fraud_detector", "risk_screen_completed",
                               "Explicit profile risk signals were checked and treated as review context, not proof",
                               provider="rules-engine"))
            precedence_notes, insufficient = self._precedence(category, evidence, facts)
            verified_ids = [e.evidence_id for e in evidence
                            if e.verification.status.value == "verified"]
            if not verified_ids or not self._deciding_evidence_present(category, evidence, (getattr(case, "category_details", {}) or {}).get("fee_type")) or profile_flags:
                insufficient = True
            if model_skip_reasons:
                insufficient = True
                precedence_notes = list(dict.fromkeys([*precedence_notes, *model_skip_reasons]))
            contradiction_note = self._fare_contradiction(category, case, facts)
            try:
                if model_skip_reasons:
                    judge_out = {
                        "ruling_type": "no_action",
                        "recommended_action": {"description": "No automated ruling is proposed; a human reviewer must resolve the recorded gap.", "delivery": "none", "amount": None},
                        "confidence": 0.0,
                        "reasoning": "The available evidence and published policy do not support a safe automatic ruling. " + "; ".join(model_skip_reasons),
                        "evidence_references": [],
                        "policy_references": policy_ctx.rule_ids(),
                        "measurements": policy_ctx.measurement_map(),
                        "decisive_facts": [],
                        "provider": {"kind": "rules-engine", "model": "ryde-policy-rules-1", "display_name": "rules-based review"},
                        "_synthetic": False,
                    }
                elif not repair_resolved:
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
                    evidence_records=[e.to_api() for e in evidence],
                    dispute=dispute,
                    judging_weights={
                        "policy_priority": self.judging_config.policy_priority,
                        "human_approved_weight": self.judging_config.human_approved_weight,
                        "model_proposed_weight": self.judging_config.model_proposed_weight,
                        "recency_half_life_days": self.judging_config.recency_half_life_days,
                        "fraud_influence_weight": self.judging_config.fraud_influence_weight,
                        "fraud_assessment_note": self.judging_config.fraud_assessment_note,
                    },
                    )
            except (ProviderUnavailable, ModelOutputInvalid) as exc:
                if provider.meta.kind != "llm" or _fallback_attempted:
                    raise
                if isinstance(exc, ProviderUnavailable):
                    status = re.search(r"\bHTTP\s+(\d{3})\b", str(exc))
                    detail = str(exc).lower()
                    if status:
                        reason = f"provider unavailable (HTTP {status.group(1)})"
                    elif "timeout" in detail or "timed out" in detail:
                        reason = "provider request timed out"
                    elif any(token in detail for token in ("connect", "network", "dns")):
                        reason = "provider connection failed"
                    else:
                        reason = "provider unavailable"
                else:
                    reason = "invalid structured model output"
                trace.append(event(
                    "system", "fallback",
                    f"Judge review fallback: {reason}; live Judge output was not accepted",
                    provider=provider.meta.display_name,
                ))
                return self.run_case(
                    case,
                    _provider=self.fallback_provider,
                    _fallback_attempted=True,
                    _trace=trace,
                    _force_human_review_reason=reason,
                )
        if official:
            gaps = validate_final_output(category, facts, case.filed_at, judge_out, audit_findings,
                                         [rider_out,driver_out], evidence, policy_ctx)
            # The provider may still propose a confident ruling despite conflicting
            # authoritative fare sources. Keep this final gate independent of the
            # Judge prompt and require human review until the discrepancy is resolved.
            contradiction_note = self._fare_contradiction(category, case, facts)
            if contradiction_note:
                gaps.append(contradiction_note)
            by_id = {e.evidence_id:e for e in evidence}
            if any(not f.get("evidence_references") or any(
                ref not in by_id or by_id[ref].verification.status.value != "verified"
                for ref in f.get("evidence_references", [])) for f in judge_out.get("decisive_facts", [])):
                gaps.append("Decisive facts lack verified supporting records.")
            if gaps:
                insufficient = True
                precedence_notes.extend(gaps)
            # No automatic denial is inferred from a high-confidence proposal with absent facts.
            trace.append(event("independent_validator", "final_validation", "; ".join(gaps) if gaps else "Policy citations, evidence references, decisive facts, and remedy eligibility passed", provider="rules-engine"))
        if _force_human_review_reason:
            insufficient = True
            judge_out["reasoning"] = (
                f"{judge_out.get('reasoning', '')} Live AI review could not be validated ({_force_human_review_reason}); "
                "this fallback proposal requires a human decision."
            ).strip()
            trace.append(event("independent_validator", "human_review_required",
                               f"Live AI review failed: {_force_human_review_reason}; fallback cannot auto-resolve"))
        trace.append(event("judge", "ruling_proposed", judge_out.get("reasoning", ""), judge_out.get("evidence_references", []), provider.meta.display_name))

        # Point 1 — structural: a refund/compensation MUST carry a positive amount. A figureless
        # monetary remedy is downgraded to no_action here (all categories), and the case becomes
        # insufficient so it escalates rather than emitting a remedy with no figure.
        judge_out, downgraded = finalize_ruling(judge_out)
        if downgraded:
            insufficient = True
        if official:
            contradiction_note = None
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
        if not official:
            judge_out["evidence_references"] = relied_on or evidence_ids
        if category == "safety_incident" and not official:
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
                "summary": str(f.content),
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
                "reasons": [{"safety_incident":"safety_category", "insufficient_or_contradictory_evidence":"insufficient_evidence", "exceeds_refund_cap":"exceeds_ruling_cap", "exceeds_goodwill_cap":"exceeds_ruling_cap"}.get(reason,reason) for reason in esc.reasons],
                "human_review_summary": summary,
            },
            "provider": judge_out["provider"],
        }
        # Last-line invariant: a refund/compensation in the returned payload MUST carry a
        # positive amount. finalize_ruling above already downgrades a figureless remedy, so this
        # only fires on a logic error — and then it fails loud rather than emitting a bad ruling.
        assert_ruling_integrity(judge_block)

        trace.append(event("system", "completed", "Human review required" if esc.escalated else "Automatically resolved"))
        result = {
            "trace": trace,
            "party_explanations": {
                "rider": ("Review required. " if esc.escalated else "Decision: ") + judge_block["reasoning"] + " " + judge_block["recommended_action"].get("description", ""),
                "driver": ("Review required. " if esc.escalated else "Decision: ") + judge_block["reasoning"] + " No funds or vouchers have been executed.",
            },
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
            "model_proposed_ruling": ({
                "ruling_type": judge_block["ruling_type"],
                "recommended_action": judge_block["recommended_action"],
                "author_type": "model",
                "decision_origin": "agent",
                "author_id": judge_block["provider"]["model"],
                "credibility": "model_proposed",
            } if judge_block["provider"].get("kind") != "rules-engine" else None),
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

    def run_review_triage(self, case) -> dict[str, Any]:
        """Run source retrieval and evidence triage for categories reserved for a human.

        This path does not call a generative provider and does not emit a fault finding or
        proposed remedy. It gives the reviewer a verified evidence inventory and next steps.
        """
        facts = assemble_facts(self.reader, case)
        evidence = assemble_evidence_bundle(
            self.reader, case, allocate_evidence_id=self.store.allocate_evidence_id, facts=facts
        )
        self.store.save_evidence_bundle(case.case_id, [item.to_api() for item in evidence])
        verified = [item for item in evidence if item.verification.status.value == "verified"]
        unverified = [item for item in evidence if item.verification.status.value != "verified"]
        category = case.category
        requirements = {
            "property_damage": ["damage or cleaning photos, including a photo showing the vehicle plate", "itemised cleaning receipt and required business details", "cleaning within 24 hours and claim within 48 hours"],
            "safety_incident": ["preserve trip, event, and communication records", "urgent human safety review"],
            "lost_item": ["item description", "last known location", "reported or return status"],
            "conduct_complaint": ["incident description", "relevant platform messages", "human investigation"],
        }[category]
        next_steps = [f"Check: {item}." for item in requirements]
        if unverified:
            next_steps.append(f"Review {len(unverified)} submitted or unverified evidence item(s) before relying on them.")
        if not verified:
            next_steps.append("No verified supporting records were found; request or locate evidence before deciding.")
        details = getattr(case, "category_details", {}) or {}
        damage_cap = None
        if category == "property_damage":
            damage_cap = {"minor_spillage": 4000, "stains_or_bodily_fluids": 12000,
                          "vomit": 20000}.get(details.get("claim_type"))
            if damage_cap is not None:
                next_steps.append(
                    f"The reported claim type has a published maximum of S${damage_cap / 100:.2f}; "
                    "this is a reference cap only and Ryde retains approval discretion."
                )
        reported_item_status = None
        if category == "lost_item":
            candidate_status = str(details.get("reported_item_status", "")).strip().lower()
            if candidate_status in {"reported", "found", "returned", "unresolved"}:
                reported_item_status = candidate_status
                next_steps.append(f"The filer reports the item status as ‘{candidate_status}’; verify it with the parties.")
        urgency = 1.0 if category == "safety_incident" else (0.8 if category == "conduct_complaint" else 0.45)
        provider = {"kind": "rules-engine", "model": "ryde-evidence-triage-1",
                    "display_name": "automated evidence triage", "policy_version": self.policy.version}
        policy_context = evaluator.evaluate(category, facts, self.policy)
        policy_sources = []
        for rule_id in policy_context.rule_ids():
            rule = self.policy.rule(rule_id)
            if rule:
                policy_sources.append({"rule_id": rule.rule_id, "text": rule.text,
                                       "source": rule.source})
        trace = [event("system", "evidence_assembled", "Retrieved and saved the trip evidence snapshot",
                       [item.evidence_id for item in evidence]),
                 event("rider_advocate", "submission_summarized",
                       f"Filing statement recorded; {len(verified)} verified and {len(unverified)} unverified evidence item(s) available."),
                 event("driver_advocate", "submission_summarized",
                       "The linked trip records were checked for context; no fault finding was made."),
                 event("evidence_auditor", "audit_completed",
                       f"Verified {len(verified)} record(s); {len(unverified)} item(s) require review.",
                       [item.evidence_id for item in verified], "rules-engine"),
                 event("judge", "human_review_recommended",
                       "This category requires human review under the current policy and operating rules."),
                 event("system", "completed", "Evidence triage completed; final decision remains with a reviewer.")]
        self.store.persist_model_work(case.case_id, {
            "category": category, "policy_version": self.policy.version,
            "triage": {"verified_evidence_count": len(verified),
                       "unverified_evidence_count": len(unverified), "next_steps": next_steps},
        })
        ride = facts.get("ride") or {}
        return {
            "case_id": case.case_id, "ride_id": case.ride_id, "category": category,
            "status": "pending_review", "synthetic": bool(ride.get("synthetic", True)),
            "synthetic_reasoning": False, "policy_version": self.policy.version,
            "created_at": case.filed_at, "case_facts": self._case_facts_view(facts),
            "evidence_audit": {"findings": [], "provider": provider,
                               "verified_count": len(verified), "unverified_count": len(unverified)},
            "fraud_assessment": None, "advocates": None, "judge": None,
            "model_proposed_ruling": None, "reviewer_approved_ruling": None,
            "triage": {"automated": True, "final_decision_required": True,
                       "next_steps": next_steps,
                       "reported_category_details": details,
                       "published_claim_cap_cents": damage_cap,
                       "reported_item_status": reported_item_status,
                       "policy_sources": policy_sources,
                       "verified_evidence_ids": [item.evidence_id for item in verified],
                       "unverified_evidence_ids": [item.evidence_id for item in unverified]},
            "trace": trace,
            "human_review_summary": "Automated evidence triage is complete. A human must investigate and decide this case.",
            "external_findings": [], "external_unavailable": False, "urgency": urgency,
            "case_history": [],
        }

    # --- helpers -------------------------------------------------------------
    def _thresholds(self) -> dict[str, float]:
        t = dict(self.policy.threshold_map())
        t.setdefault("confidence_threshold", self.settings.escalation_confidence_threshold)
        t.setdefault("goodwill_cap_cents", self.settings.goodwill_cap_cents)
        return t

    def _fare_contradiction(self, category, case, facts) -> str | None:
        """A material contradiction between the filing and verified fare records.
        Returns a human-readable note or None.

        - no_show_charge: the filing disputes a cancellation fee, but the verified fare record shows
          `cancellation_fee_cents == 0` — no fee was ever charged.
        - route_deviation: ride-header and fare-ledger totals disagree, or the filing claims an
          overcharge but the verified ride record shows the rider was charged no more than quoted.
        Only flagged when the filing actually asserts the charge (a no_show_charge filing inherently
        disputes a fee; a claimed_amount, if present, is corroborating)."""
        ride = facts.get("ride") or {}
        fare = facts.get("fare") or {}
        if category in {"no_show_charge", "other_cancellation_fee"}:
            fee_type = getattr(case, "category_details", {}).get("fee_type")
            fee_key = "waiting_fare_cents" if category == "other_cancellation_fee" and fee_type == "rider_waiting" else "cancellation_fee_cents"
            fee = int(fare.get(fee_key, ride.get("charged_fare_cents", 0)) or 0)
            if fee == 0:
                return ("filing disputes a cancellation fee, but the verified fare record shows "
                        f"no fee was charged ({fee_key}=0)")
        if category in {"route_deviation", "fare_calculation"}:
            ledger_total = fare.get("total_fare_cents")
            if (ride.get("verification_status") == "verified"
                    and fare.get("verification_status") == "verified"
                    and ride.get("charged_fare_cents") is not None
                    and ledger_total is not None
                    and int(ride["charged_fare_cents"]) != int(ledger_total)):
                return ("verified ride charge and fare-ledger total disagree "
                        f"({ride['charged_fare_cents']}c vs {ledger_total}c)")
            claimed = getattr(case, "claimed_amount_cents", None)
            charged = int(ride.get("charged_fare_cents", 0) or 0)
            quoted = int(ride.get("quoted_fare_cents", 0) or 0)
            if category == "route_deviation" and claimed and charged <= quoted:
                return ("filing claims an overcharge, but the verified fare record shows "
                        f"charged {charged}c <= quoted {quoted}c (no overcharge)")
        return None

    def _relied_on_evidence_ids(self, category, evidence: list[Evidence]) -> list[str]:
        """The verified records whose factual question the ruling turns on."""
        questions = {"route_deviation": {"distance", "fare", "stops"},
                     "no_show_charge": {"arrival", "contact", "fare"},
                     "fare_calculation": {"fare"},
                     "other_cancellation_fee": {"arrival", "contact", "fare"}}.get(category, set())
        out: list[str] = []
        for e in evidence:
            if e.verification.status.value != "verified":
                continue
            if e.payload.get("_question") in questions:
                out.append(e.evidence_id)
        return out

    def _deciding_evidence_present(self, category, evidence: list[Evidence], fee_type: str | None = None) -> bool:
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

        from app.policy.loader import is_source_backed_policy

        if category == "route_deviation":
            return verified_payload_has("actual_distance_km") and verified_payload_has("planned_distance_km")
        if category == "no_show_charge":
            if is_source_backed_policy(self.policy.version):
                return verified_payload_has("cancellation_fee_cents") and (verified_payload_has("accepted_at") or any(
                    e.verification.status.value == "verified" and e.payload.get("event_type") in {"matched","driver_matched","accepted"} for e in evidence))
            return verified_payload_has("min_distance_to_pickup_m")
        if category == "fare_calculation":
            return all(verified_payload_has(key) for key in
                       ("charged_fare_cents", "total_fare_cents", "components"))
        if category == "other_cancellation_fee":
            if fee_type == "rider_waiting":
                return all(verified_payload_has(key) for key in
                           ("waiting_fare_cents", "driver_waited_seconds", "completed_at"))
            return all(verified_payload_has(key) for key in
                       ("cancellation_fee_cents", "cancellation_actor", "cancellation_timestamp"))
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
