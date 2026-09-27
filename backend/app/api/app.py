"""FastAPI app factory and core dispute routes (contract §2–4).

Wiring: `create_app(container)` builds the app around an injected Container so tests supply a
fixture reader and the same code serves Postgres at integration. Every MUTATING route requires
`X-Reviewer-Id` (D-07). Adjudication is idempotent and CONCURRENCY-safe via the result store's
claim protocol. Dashboard and company-import endpoints are registered by their focused modules.
A failure never returns a ruling (contract §1).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.archive_presenter import _archive_case_result
from app.api.company_import import register_company_import_route
from app.api.container import Container
from app.api.metrics_routes import register_metrics_routes
from app.api.metrics_helpers import _as_utc, _parse_datetime
from app.domain import (
    AUTOMATED_ADJUDICATION_CATEGORIES,
    DisputeCategory,
    FiledBy,
    OVERRIDE_REASON_CODES,
    RulingType,
)
from app.persistence.reader import (
    CaseRecord,
    DatabaseUnavailable,
    EvidenceRef,
    LiveIdRejected,
)
from app.persistence.store import IdempotencyConflict, is_first_claim
from app.providers.base import ModelOutputInvalid, ProviderUnavailable


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(code: str, message: str, status: int, details: dict | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return JSONResponse(status_code=status, content=body)


def _next_case_id(store) -> str:
    return store.allocate_case_id()


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="Ryde Tribunal", version="0.2.0")
    # FIX 5: allow the frontend dev origin so it can call the API directly, without its
    # Next.js rewrites proxy. Phase Zero dev origin only (D-07 single reviewer identity).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    store = container.store
    reader = container.reader
    orch = container.orchestrator()

    @app.exception_handler(SQLAlchemyError)
    async def persistence_unavailable(_request: Request, exc: SQLAlchemyError):
        # Writes to the backend-owned tribunal schema are database operations too. A failed
        # persistence step must not return a ruling-shaped success response.
        return _err("database_unavailable", "datastore unreachable", 503)

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        db_ok = "ok"
        try:
            reader.get_ride("__healthcheck__")
        except DatabaseUnavailable:
            db_ok = "unavailable"
        except Exception:
            db_ok = "ok"  # not-found is fine
        provider_ok = "ok" if container.provider.meta.kind == "deterministic-mock" else "ok"
        return {"status": "ok", "database": db_ok, "provider": provider_ok}

    @app.post("/api/v1/disputes")
    def file_dispute(payload: dict, x_reviewer_id: str | None = Header(default=None)):
        if not x_reviewer_id:
            return _err("validation_error", "X-Reviewer-Id header required", 401)
        try:
            category = DisputeCategory(payload["category"])
            filed_by = FiledBy(payload["filed_by"])
            ride_id = payload["ride_id"]
            subject = payload["subject"]
            description = payload["description"]
        except (KeyError, ValueError) as exc:
            return _err("validation_error", f"invalid dispute body: {exc}", 422)

        case_id = _next_case_id(store)
        # The filed dispute + its party submissions live in the backend's OWN schema
        # (tribunal.case_*, write matrix §6). Attachments are party-submitted evidence, stored
        # unverified; verified system records are assembled from ride_data at adjudication.
        # Party and system evidence IDs share the backend's global sequence.
        attachments = payload.get("attachments") or []
        evidence_refs = [
            EvidenceRef(
                evidence_id=store.allocate_evidence_id(),
                class_=att.get("class", "attachment"),
                source=f"{filed_by.value}_submitted",
                visibility="both",
                verification_status="unverified",
                verification_method="party_submitted",
                recorded_at=_now(),
                provenance={"origin": "party_submission"},
                payload=att.get("payload", {}),
            )
            for i, att in enumerate(attachments)
        ]
        case = CaseRecord(
            case_id=case_id,
            ride_id=ride_id,
            category=category.value,
            filed_by=filed_by.value,
            subject=subject,
            description=description,
            claimed_amount_cents=(payload.get("claimed_amount") or {}).get("amount_cents"),
            currency=(payload.get("claimed_amount") or {}).get("currency", container.settings.currency),
            filed_at=_now(),
            evidence=evidence_refs,
        )
        store.save_filed_case(case)
        store.append_history(case_id, {
            "event": "filed", "actor_type": "reviewer", "actor_id": x_reviewer_id,
            "at": case.filed_at, "payload": {"category": category.value},
        })
        return JSONResponse(status_code=201, content={"case_id": case_id, "status": "queued"})

    @app.post("/api/v1/disputes/{case_id}/adjudicate")
    def adjudicate(
        case_id: str,
        request: Request,
        x_reviewer_id: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ):
        if not x_reviewer_id:
            return _err("validation_error", "X-Reviewer-Id header required", 401)

        # Resolve the LIVE case from the backend's OWN schema (tribunal.case_*). There is no
        # reader accessor for it — the live case belongs to the backend end to end (§6). The
        # ride/evidence FACTS are assembled from ride_data reads inside run_case.
        case = store.get_filed_case(case_id)
        if case is None:
            return _err("not_found", f"case {case_id} not found", 404)

        body_hash = hashlib.sha256(
            json.dumps({"case_id": case_id}, sort_keys=True).encode()
        ).hexdigest()

        if idempotency_key:
            try:
                claim = store.claim_idempotency(idempotency_key, body_hash)
            except IdempotencyConflict:
                return _err("conflict", "idempotency key reused with different body", 409)
            if not is_first_claim(claim):
                # Someone else owns this key; wait for their result.
                claim.event.wait(timeout=30)
                done_case = store.idempotent_case_id(idempotency_key)
                existing = store.get_case_result(done_case) if done_case else None
                if existing:
                    return existing
                return _err("conflict", "concurrent adjudication did not complete", 409)

        try:
            if case.category not in {c.value for c in AUTOMATED_ADJUDICATION_CATEGORIES}:
                # The category is in the approved filing vocabulary but has no automated
                # policy implementation. Keep the filed record and route it to a reviewer;
                # do not call the model or emit a proposed ruling.
                ride = reader.get_ride(case.ride_id)
                result = _pending_review_result(
                    case, container.policy.version,
                    synthetic=bool(ride.synthetic) if ride is not None else True,
                )
            else:
                result = orch.run_case(case)
        except DatabaseUnavailable:
            return _err("database_unavailable", "datastore unreachable", 503)
        except ProviderUnavailable:
            return _err("provider_unavailable", "model provider unreachable", 503)
        except ModelOutputInvalid as exc:
            return _err("model_output_invalid", str(exc), 502)

        store.save_case_result(result)
        judge = result.get("judge") or {}
        store.append_history(case_id, {
            "event": "adjudicated" if judge else "routed_to_human_review",
            "actor_type": "agent" if judge else "system",
            "actor_id": judge.get("provider", {}).get("model", "category_router"), "at": _now(),
            "payload": {"ruling_type": judge.get("ruling_type"),
                        "status": result["status"]},
        })
        if idempotency_key:
            store.complete_idempotency(idempotency_key, case_id)
        return _with_history(store, result)

    @app.get("/api/v1/disputes/{case_id}")
    def get_dispute(case_id: str):
        result = store.get_case_result(case_id)
        if result is not None:
            return _with_history(store, result)

        # Live and archive IDs share the same shape; source comes from the table that contains
        # the ID, not a prefix test. A filed live case may not have been adjudicated yet. Return
        # its filing data as queued without running models or inventing ride facts/outcomes.
        filed_case = store.get_filed_case(case_id)
        if filed_case is not None:
            try:
                ride = reader.get_ride(filed_case.ride_id)
            except DatabaseUnavailable:
                return _err("database_unavailable", "ride data is unavailable", 503)
            # Match adjudicated/pending-review results: the linked ride determines whether
            # the record is synthetic. If the ride is missing, retain the existing conservative
            # default used by the orchestrator rather than claiming it is company data.
            synthetic = bool(ride.synthetic) if ride is not None else True
            queued = _queued_case_result(
                filed_case, container.policy.version, synthetic=synthetic
            )
            return _with_history(store, queued)
        try:
            archived = reader.get_archive_case(case_id)
        except DatabaseUnavailable:
            return _err("database_unavailable", "historical archive is unavailable", 503)
        except AttributeError:
            return _err("database_unavailable", "historical archive lookup is not configured", 503)
        except LiveIdRejected:
            archived = None
        if archived is None:
            return _err("not_found", f"case {case_id} not found", 404)
        return _archive_case_result(
            archived, container.settings.escalation_confidence_threshold
        )

    @app.get("/api/v1/disputes")
    def list_disputes(
        status: str | None = None,
        category: str | None = None,
        urgency_min: float | None = None,
        needs_review: bool | None = None,
        from_: datetime | None = Query(default=None, alias="from"),
        to: datetime | None = None,
        sort: str = "-created_at",
        limit: int = 50,
        cursor: str | None = None,
    ):
        # Live filings and archived historical cases use distinct IDs but share this view.
        rows, error = _filed_rows(
            store, reader, container.settings.escalation_confidence_threshold
        )
        if error:
            return error
        if not 1 <= limit <= 200:
            return _err("validation_error", "limit must be between 1 and 200", 422)
        try:
            offset = int(cursor) if cursor is not None else 0
        except ValueError:
            return _err("validation_error", "cursor must be a non-negative integer", 422)
        if offset < 0:
            return _err("validation_error", "cursor must be a non-negative integer", 422)
        if sort not in {"created_at", "-created_at", "urgency", "-urgency",
                        "confidence", "-confidence"}:
            return _err("validation_error", "unsupported sort value", 422)
        items = []
        for row in rows:
            case, result = row["case"], row["result"]
            view = _case_list_view(case, result)
            filed_at = _parse_datetime(view["created_at"])
            if status and view["status"] != status:
                continue
            if category and view["category"] != category:
                continue
            if urgency_min is not None and view["urgency"] < urgency_min:
                continue
            if needs_review is not None and view["needs_review"] != needs_review:
                continue
            if from_ and filed_at < _as_utc(from_):
                continue
            if to and filed_at > _as_utc(to):
                continue
            items.append(_summary(result, view["needs_review"], case=case))
        reverse = sort.startswith("-")
        field = sort.lstrip("-")
        items.sort(key=lambda item: (
            item.get(field) if item.get(field) is not None else -1,
            item["created_at"], item["case_id"],
        ), reverse=reverse)
        page = items[offset : offset + limit]
        next_offset = offset + len(page)
        return {
            "items": page,
            "next_cursor": str(next_offset) if next_offset < len(items) else None,
        }

    @app.get("/api/v1/evidence/{evidence_id}")
    def get_evidence(evidence_id: str):
        # Scoping is SERVER-SIDE: the evidence id is globally unique and each record carries its
        # own case_id, so the client sends only the id (contract §4). No case_id query param.
        bundled = store.find_evidence_global(evidence_id)
        if bundled is not None:
            return bundled  # already carries its own case_id
        # Party submissions on a filed (not-yet-adjudicated) case.
        found = store.find_party_evidence_global(evidence_id)
        if found is not None:
            case_id, ref = found
            return {
                "evidence_id": ref.evidence_id,
                "case_id": case_id,
                "class": ref.model_dump().get("class_", "attachment"),
                "source": ref.source,
                "recorded_at": ref.recorded_at,
                "provenance": ref.provenance,
                "verification": {
                    "status": ref.verification_status,
                    "method": ref.verification_method,
                    "uncertainty_pct": ref.verification_uncertainty_pct,
                },
                "visibility": ref.visibility,
                "payload": ref.payload,
            }
        return _err("not_found", f"evidence {evidence_id} not found", 404)

    @app.post("/api/v1/disputes/{case_id}/approve")
    def approve(case_id: str, payload: dict, x_reviewer_id: str | None = Header(default=None)):
        if not x_reviewer_id:
            return _err("validation_error", "X-Reviewer-Id header required", 401)
        result = store.get_case_result(case_id)
        if result is None:
            return _err("not_found", "case has no result to approve", 404)
        if result.get("judge") is None:
            return _err("validation_error", "there is no model-proposed ruling to approve", 422)
        event = {
            "event": "approved", "actor_type": "reviewer", "actor_id": x_reviewer_id,
            "at": _now(), "payload": {"note": payload.get("note", "")},
        }
        store.append_history(case_id, event)
        result = dict(result)
        result["status"] = "resolved"
        result["reviewer_approved_ruling"] = {
            "ruling_type": result["judge"]["ruling_type"],
            "recommended_action": result["judge"]["recommended_action"],
            "author_type": "human_reviewer",
            "decision_origin": "human",
            "author_id": x_reviewer_id,
            "approved_at": event["at"],
            "credibility": "higher_than_model_proposed",
        }
        store.save_case_result(result)
        return _with_history(store, result)

    @app.post("/api/v1/disputes/{case_id}/override")
    def override(case_id: str, payload: dict, x_reviewer_id: str | None = Header(default=None)):
        if not x_reviewer_id:
            return _err("validation_error", "X-Reviewer-Id header required", 401)
        result = store.get_case_result(case_id)
        if result is None:
            return _err("not_found", "case has no result to override", 404)
        if result.get("judge") is None:
            return _err("validation_error", "there is no model-proposed ruling to override", 422)
        reason_code = payload.get("reason_code")
        if reason_code not in OVERRIDE_REASON_CODES:
            return _err(
                "validation_error",
                f"reason_code must be one of {sorted(OVERRIDE_REASON_CODES)}",
                422,
            )
        try:
            ruling_type = RulingType(payload["ruling_type"]).value
        except (KeyError, ValueError):
            return _err("validation_error", "invalid ruling_type", 422)

        # Append the override; NEVER destroy the original ruling.
        event = {
            "event": "overridden", "actor_type": "reviewer", "actor_id": x_reviewer_id,
            "at": _now(),
            "payload": {
                "ruling_type": ruling_type,
                "recommended_action": payload.get("recommended_action", {}),
                "reason_code": reason_code,
                "rationale": payload.get("rationale", ""),
                "original_ruling_type": result["judge"]["ruling_type"],
            },
        }
        store.append_history(case_id, event)
        result = dict(result)
        result["status"] = "overridden"  # the original judge block is untouched
        result["reviewer_approved_ruling"] = {
            "ruling_type": ruling_type,
            "recommended_action": payload.get("recommended_action", {}),
            "reason_code": reason_code,
            "rationale": payload.get("rationale", ""),
            "author_type": "human_reviewer",
            "decision_origin": "human",
            "author_id": x_reviewer_id,
            "approved_at": event["at"],
            "credibility": "higher_than_model_proposed",
        }
        store.save_case_result(result)
        return _with_history(store, result)

    @app.get("/api/v1/disputes/{case_id}/history")
    def history(case_id: str):
        return store.get_history(case_id)

    @app.get("/api/v1/policy/{version}")
    def policy(version: str):
        if version != container.policy.version:
            return _err("not_found", f"policy {version} not loaded", 404)
        return container.policy.as_public_document()

    @app.get("/api/v1/archive/disputes")
    def list_archive_disputes(limit: int = Query(default=200, ge=1, le=1000)):
        """List historical archive cases separately from the live reviewer caseload."""
        try:
            cases = reader.list_archive_disputes(limit)
        except DatabaseUnavailable:
            return _err("database_unavailable", "historical archive is unavailable", 503)
        except AttributeError:
            return _err("database_unavailable", "historical archive listing is not configured", 503)
        items = []
        for case in cases:
            item = case.model_dump(mode="json")
            item["status"], _needs_review = _archive_dashboard_status(
                case, container.settings.escalation_confidence_threshold
            )
            items.append(item)
        return {
            "items": items,
            "statistics": {
                "total": len(items),
                "reviewer_approved": sum(
                    1 for item in items
                    if any(ruling.get("stage") == "reviewer_approved" for ruling in item["rulings"])
                ),
                "model_only": sum(
                    1 for item in items
                    if item["rulings"] and not any(
                        ruling.get("stage") == "reviewer_approved" for ruling in item["rulings"]
                    )
                ),
                "escalated": sum(1 for item in items if item["verdict"] == "escalated"),
                "ongoing": sum(1 for item in items if item["status"] in {"pending_review", "escalated"}),
            },
        }

    @app.get("/api/v1/trips")
    def search_trips(query: str = Query(default="", max_length=200),
                     limit: int = Query(default=20, ge=1, le=50)):
        try:
            results = reader.search_rides(query, limit)
        except DatabaseUnavailable:
            return _err("database_unavailable", "datastore unreachable", 503)
        except AttributeError:
            return _err("database_unavailable", "trip search is not configured", 503)
        return {"items": [
            {
                "ride_id": item["ride_id"],
                "company_trip_id": item.get("company_trip_id"),
                "booked_at": item.get("booked_at"),
                "status": item.get("ride_status"),
                "pickup_label": item.get("pickup_label"),
                "dropoff_label": item.get("dropoff_label"),
                "rider_name": item.get("rider_name"),
                "driver_name": item.get("driver_name"),
            }
            for item in results
        ]}

    register_metrics_routes(
        app, container, store, reader, _err, _filed_rows, _is_human_review
    )
    register_company_import_route(app, container, _err)
    return app


def _summary(
    r: dict[str, Any] | None,
    needs_review: bool,
    *,
    case: CaseRecord,
) -> dict[str, Any]:
    r = r or {}
    judge = r.get("judge") or {}
    provider = judge.get("provider") or {}
    provider_name = provider.get("display_name")
    if provider.get("kind") == "deterministic-mock":
        provider_name = "local deterministic"
    return {
        "case_id": case.case_id,
        "case_source": "archive" if r.get("_is_archive") else "live",
        "ride_id": case.ride_id,
        "category": case.category,
        "status": r.get("status", "queued"),
        "confidence": judge.get("confidence"),
        "ruling_type": judge.get("ruling_type"),
        "urgency": r.get("urgency", 0.0),
        "needs_review": needs_review,
        "created_at": case.filed_at,
        "synthetic_reasoning": bool(r.get("synthetic_reasoning", False)),
        "filed_by": case.filed_by,
        "provider": provider_name,
    }


def _case_list_view(case: CaseRecord, result: dict[str, Any] | None) -> dict[str, Any]:
    result = result or {}
    status = result.get("status", "queued")
    urgency = result.get("urgency", 0.0)
    return {
        "status": status,
        "urgency": urgency,
        "needs_review": (
            bool(result.get("_archive_needs_review"))
            if result.get("_is_archive") else _is_human_review(case, result)
        ),
        "created_at": case.filed_at,
    }


def _is_human_review(case: CaseRecord, result: dict[str, Any] | None) -> bool:
    if result and result.get("_is_archive"):
        return bool(result.get("_archive_needs_review"))
    if case.category not in {item.value for item in AUTOMATED_ADJUDICATION_CATEGORIES}:
        return True
    result = result or {}
    judge = result.get("judge") or {}
    return result.get("status") in {"escalated", "pending_review"} or bool(
        (judge.get("escalation") or {}).get("escalated", False)
    )


def _filed_rows(
    store, reader=None, confidence_threshold: float = 0.70
) -> tuple[list[dict[str, Any]], JSONResponse | None]:
    try:
        rows = store.list_filed_cases()
    except DatabaseUnavailable:
        return [], _err("database_unavailable", "datastore unreachable", 503)
    except AttributeError:
        return [], _err("database_unavailable", "filed-case listing is not configured", 503)
    if reader is None:
        return rows, None
    try:
        archived = reader.list_archive_disputes(None)
    except DatabaseUnavailable:
        return [], _err("database_unavailable", "historical archive is unavailable", 503)
    except AttributeError:
        return [], _err("database_unavailable", "historical archive listing is not configured", 503)
    for record in archived:
        status, needs_review = _archive_dashboard_status(record, confidence_threshold)
        case = CaseRecord(
            case_id=record.archive_case_id,
            ride_id=record.archive_ride_id,
            category=record.category,
            filed_by=record.filed_by,
            subject=record.subject,
            description=record.subject,
            filed_at=record.created_at,
        )
        rows.append({
            "case": case,
            "result": {
                "status": status,
                "urgency": 0.0,
                "_is_archive": True,
                "_archive_needs_review": needs_review,
                "judge": {
                    "confidence": record.confidence,
                    "ruling_type": record.ruling_type,
                    "provider": {},
                },
            },
        })
    return rows, None


def _archive_dashboard_status(record, confidence_threshold: float) -> tuple[str, bool]:
    proposal = next(
        (ruling for ruling in record.rulings if ruling.get("stage") == "model_proposed"),
        None,
    )
    proposal_confidence = proposal.get("confidence") if proposal else record.confidence
    proposal_escalated = (
        proposal.get("verdict") == "escalated" if proposal else record.verdict == "escalated"
    )
    needs_review = record.human_reviewed or proposal_escalated or (
        proposal_confidence is None or proposal_confidence < confidence_threshold
    )
    if record.verdict == "escalated" and not record.human_reviewed:
        return "escalated", True
    if record.human_reviewed:
        return "resolved", True
    if proposal_escalated:
        return "escalated", True
    if proposal_confidence is None or proposal_confidence < confidence_threshold:
        return "pending_review", True
    return "resolved", needs_review



def _pending_review_result(
    case: CaseRecord, policy_version: str, *, synthetic: bool
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "ride_id": case.ride_id,
        "category": case.category,
        "status": "pending_review",
        "synthetic": synthetic,
        "synthetic_reasoning": False,
        "policy_version": policy_version,
        "created_at": case.filed_at,
        "case_facts": {},
        "evidence_audit": None,
        "fraud_assessment": None,
        "advocates": None,
        "judge": None,
        "model_proposed_ruling": None,
        "reviewer_approved_ruling": None,
        "human_review_summary": f"Category {case.category} is retained but not configured for automated adjudication.",
        "external_findings": [],
        "external_unavailable": False,
        "urgency": 1.0,
        "case_history": [],
    }


def _queued_case_result(
    case: CaseRecord, policy_version: str, *, synthetic: bool
) -> dict[str, Any]:
    """Represent a newly filed live dispute without implying adjudication has run."""
    return {
        "case_id": case.case_id,
        "case_source": "live",
        "ride_id": case.ride_id,
        "category": case.category,
        "status": "queued",
        "synthetic": synthetic,
        "synthetic_reasoning": False,
        "policy_version": policy_version,
        "created_at": case.filed_at,
        "case_facts": {
            "filing": {
                "filed_by": case.filed_by,
                "subject": case.subject,
                "description": case.description,
                "claimed_amount_cents": case.claimed_amount_cents,
                "currency": case.currency,
            },
            "submitted_evidence_ids": [item.evidence_id for item in case.evidence],
        },
        "evidence_audit": None,
        "fraud_assessment": None,
        "advocates": None,
        "judge": None,
        "model_proposed_ruling": None,
        "reviewer_approved_ruling": None,
        "human_review_summary": None,
        "external_findings": [],
        "external_unavailable": False,
        "urgency": 0.0,
        "case_history": [],
    }


def _with_history(store, result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    out["case_source"] = "live"
    out["case_history"] = store.get_history(result["case_id"])
    return out
