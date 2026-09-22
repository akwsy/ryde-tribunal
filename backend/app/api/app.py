"""FastAPI application and routes (contract §2–4).

Wiring: `create_app(container)` builds the app around an injected Container so tests supply a
fixture reader and the same code serves Postgres at integration. Every MUTATING route requires
`X-Reviewer-Id` (D-07). Adjudication is idempotent and CONCURRENCY-safe via the result store's
claim protocol. A failure never returns a ruling (contract §1).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.container import Container
from app.domain import (
    DisputeCategory,
    FiledBy,
    OVERRIDE_REASON_CODES,
    PHASE_ZERO_CATEGORIES,
    RulingType,
)
from app.persistence.reader import CaseRecord, DatabaseUnavailable, EvidenceRef
from app.persistence.store import IdempotencyConflict, is_first_claim
from app.providers.base import ProviderUnavailable


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(code: str, message: str, status: int, details: dict | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return JSONResponse(status_code=status, content=body)


def _next_case_id(store) -> str:
    return f"DSP-{store.count_filed_cases() + 45:06d}"


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="Ryde Tribunal", version="0.1.0")
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
        # Evidence ids are a clean per-case EV-\d{6} sequence (contract ^EV-\d{6}$, FIX 3) — no
        # suffix. Party submissions take a high range (900000+) so they never collide with the
        # assembled system-record ids (which derive from the ride number, far below).
        _n = store.count_filed_cases()
        _party_base = 900000 + (_n % 90) * 100
        attachments = payload.get("attachments") or []
        evidence_refs = [
            EvidenceRef(
                evidence_id=f"EV-{_party_base + i + 1:06d}",
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

        if case.category not in {c.value for c in PHASE_ZERO_CATEGORIES}:
            return _err(
                "validation_error",
                f"category {case.category} is not adjudicated end-to-end in Phase Zero",
                422,
            )

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
            result = orch.run_case(case)
        except DatabaseUnavailable:
            return _err("database_unavailable", "datastore unreachable", 503)
        except ProviderUnavailable:
            return _err("provider_unavailable", "model provider unreachable", 503)

        store.save_case_result(result)
        store.append_history(case_id, {
            "event": "adjudicated", "actor_type": "agent",
            "actor_id": result["judge"]["provider"]["model"], "at": _now(),
            "payload": {"ruling_type": result["judge"]["ruling_type"],
                        "status": result["status"]},
        })
        if idempotency_key:
            store.complete_idempotency(idempotency_key, case_id)
        return _with_history(store, result)

    @app.get("/api/v1/disputes/{case_id}")
    def get_dispute(case_id: str):
        result = store.get_case_result(case_id)
        if result is None:
            return _err("not_found", f"case {case_id} has no result", 404)
        return _with_history(store, result)

    @app.get("/api/v1/disputes")
    def list_disputes(status: str | None = None, category: str | None = None,
                      needs_review: bool | None = None, limit: int = 50):
        items = []
        for r in store.list_case_results():
            if status and r["status"] != status:
                continue
            if category and r["category"] != category:
                continue
            nr = r["status"] in ("escalated", "pending_review")
            if needs_review is not None and nr != needs_review:
                continue
            items.append(_summary(r, nr))
        return {"items": items[:limit], "next_cursor": None}

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
        event = {
            "event": "approved", "actor_type": "reviewer", "actor_id": x_reviewer_id,
            "at": _now(), "payload": {"note": payload.get("note", "")},
        }
        store.append_history(case_id, event)
        result = dict(result)
        result["status"] = "resolved"
        store.save_case_result(result)
        return _with_history(store, result)

    @app.post("/api/v1/disputes/{case_id}/override")
    def override(case_id: str, payload: dict, x_reviewer_id: str | None = Header(default=None)):
        if not x_reviewer_id:
            return _err("validation_error", "X-Reviewer-Id header required", 401)
        result = store.get_case_result(case_id)
        if result is None:
            return _err("not_found", "case has no result to override", 404)
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

    @app.get("/api/v1/metrics/overview")
    def metrics_overview(tz: str = "Asia/Singapore"):
        results = store.list_case_results()
        pending = sum(1 for r in results if r["status"] in ("escalated", "pending_review"))
        overridden = sum(1 for r in results if r["status"] == "overridden")
        auto = sum(1 for r in results if r["status"] == "resolved")
        n = len(results)
        return {
            "filed": {"today": n, "week": n, "month": n},
            "auto_resolved": auto,
            "human_review_pending": pending,
            "overridden": overridden,
        }

    @app.get("/api/v1/metrics/timeseries")
    def metrics_timeseries(granularity: str = "day", **_: Any):
        by_day: dict[str, dict[str, int]] = {}
        for r in store.list_case_results():
            day = (r.get("created_at") or _now())[:10]
            bucket = by_day.setdefault(day, {"automatic": 0, "human_intervention": 0})
            if r["status"] in ("escalated", "overridden", "pending_review"):
                bucket["human_intervention"] += 1
            else:
                bucket["automatic"] += 1
        points = [{"date": d, **v} for d, v in sorted(by_day.items())]
        return {"points": points}

    return app


def _summary(r: dict[str, Any], needs_review: bool) -> dict[str, Any]:
    return {
        "case_id": r["case_id"],
        "ride_id": r["ride_id"],
        "category": r["category"],
        "status": r["status"],
        "confidence": r["judge"]["confidence"],
        "ruling_type": r["judge"]["ruling_type"],
        "urgency": r["urgency"],
        "needs_review": needs_review,
        "created_at": r["created_at"],
        "synthetic_reasoning": r["synthetic_reasoning"],
    }


def _with_history(store, result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    out["case_history"] = store.get_history(result["case_id"])
    return out
