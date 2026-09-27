"""Present archived case records in the read-only CaseResult API shape."""

from __future__ import annotations

from typing import Any

from app.persistence.reader import ArchiveCase


def _archive_case_result(archive: ArchiveCase, confidence_threshold: float) -> dict[str, Any]:
    """Present one archive-table row through the normal read-only case detail route.

    Historical data has no live JudgeOutput or advocate transcript contract. Keep `judge` and
    `advocates` null, and expose the stored proposal and human-approved ruling separately.
    This also keeps reviewer action controls unavailable for archived decisions.
    """
    record = archive.archive_record or {}
    trip = record.get("trip_snapshot") or {}
    ride_id = archive.archive_ride_id or trip.get("archive_ride_id")
    if not ride_id:
        # Older/custom readers may only supply precedent fields. Treat missing archive detail as
        # unavailable rather than inventing a trip ID or returning an incomplete CaseResult.
        raise ValueError(f"archive case {archive.archive_case_id} has no archived trip ID")

    top_decision = record.get("decision") or {}
    raw_rulings = record.get("rulings") or archive.rulings or []
    by_stage: dict[str, dict[str, Any]] = {}
    for ruling in raw_rulings:
        if not isinstance(ruling, dict):
            continue
        decision = ruling.get("decision")
        if isinstance(decision, dict):
            by_stage[str(ruling.get("stage", ""))] = decision
        else:
            # Small fixture/read-adapter records already expose flattened rulings.
            by_stage[str(ruling.get("stage", ""))] = ruling

    human_review = record.get("human_review") or {}
    human_reviewed = bool(human_review.get("human_reviewed", archive.was_overridden))
    proposal = by_stage.get("model_proposed")
    approved = by_stage.get("reviewer_approved")
    if proposal is None and not human_reviewed and top_decision:
        proposal = top_decision
    if approved is None and human_reviewed and top_decision:
        approved = top_decision

    def recorded_ruling(decision: dict[str, Any] | None, stage: str) -> dict[str, Any] | None:
        if not decision:
            return None
        amount = decision.get("recommended_amount") or {}
        if (
            isinstance(amount, dict)
            and amount.get("amount_cents") is not None
            and int(amount["amount_cents"]) > 0
        ):
            amount_payload = {
                "amount_cents": int(amount["amount_cents"]),
                "currency": amount.get("currency", "SGD"),
            }
        else:
            amount_payload = None
        action_text = (
            decision.get("recommended_action_description")
            or decision.get("recommended_action")
            or ""
        )
        origin = decision.get("decision_origin") or (
            "human" if stage == "reviewer_approved" else "agent"
        )
        decided_at = decision.get("decided_at")
        review_reason = human_review.get("reason_code") if stage == "reviewer_approved" else None
        rationale = human_review.get("rationale") if stage == "reviewer_approved" else None
        return {
            "ruling_type": decision.get("ruling_type", "no_action"),
            "recommended_action": {"description": action_text, "amount": amount_payload},
            "author_type": "human_reviewer" if stage == "reviewer_approved" else "model",
            "decision_origin": origin,
            "author_id": None,
            "credibility": (
                "higher_than_model_proposed" if stage == "reviewer_approved"
                else "model_proposed"
            ),
            "reason_code": review_reason,
            "rationale": rationale,
            "approved_at": decided_at if stage == "reviewer_approved" else None,
        }

    model_ruling = recorded_ruling(proposal, "model_proposed")
    reviewer_ruling = recorded_ruling(approved, "reviewer_approved")
    verdict = top_decision.get("verdict", "")
    if human_reviewed:
        status = "resolved"
    elif verdict == "escalated" or archive.ruling_type == "escalated":
        status = "escalated"
    elif proposal is None or proposal.get("confidence", archive.confidence) is None or float(
        proposal.get("confidence", archive.confidence)
    ) < confidence_threshold:
        status = "pending_review"
    else:
        status = "resolved"

    created_at = record.get("created_at")
    evidence = record.get("evidence") or []
    facts = {
        "archived_trip_snapshot": trip,
        "filing_user_snapshot": record.get("filing_user_snapshot") or {},
        "archived_evidence": evidence,
        "primary_classification": record.get("primary_classification"),
        "secondary_classifications": record.get("secondary_classifications") or [],
    }
    case_history = []
    for stage, decision in by_stage.items():
        if not decision:
            continue
        case_history.append({
            "event": stage,
            "actor_type": "human" if decision.get("decision_origin") == "human" else "agent",
            "actor_id": None,
            "at": decision.get("decided_at") or created_at,
            "payload": {
                "verdict": decision.get("verdict"),
                "ruling_type": decision.get("ruling_type"),
                "recommended_action": decision.get("recommended_action_description")
                or decision.get("recommended_action"),
                "decision_origin": decision.get("decision_origin"),
            },
        })

    return {
        "case_id": archive.archive_case_id,
        "case_source": "archive",
        "ride_id": ride_id,
        "category": archive.category,
        "status": status,
        "synthetic": bool(record.get("synthetic", False)),
        # Archive records don't store provider metadata needed to assert deterministic reasoning.
        "synthetic_reasoning": False,
        "policy_version": archive.policy_version,
        "created_at": created_at,
        "case_facts": facts,
        "evidence_audit": None,
        "fraud_assessment": None,
        "advocates": None,
        "judge": None,
        "model_proposed_ruling": model_ruling,
        "reviewer_approved_ruling": reviewer_ruling,
        "human_review_summary": human_review.get("rationale") or None,
        "external_findings": [],
        "external_unavailable": False,
        "urgency": 0.0,
        "case_history": case_history,
    }
