"""Shared judge access for a single-process, synthetic-only hosted demo.

Reviewer headers remain audit labels, never credentials. Signed expiring cookies
authenticate the browser; same-origin write checks prevent cross-site actions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import OrderedDict, deque
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def hash_passcode(passcode: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(passcode.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_passcode(value: str, encoded: str) -> bool:
    try:
        scheme, salt, _ = encoded.split("$")
        return scheme == "scrypt" and hmac.compare_digest(hash_passcode(value, bytes.fromhex(salt)), encoded)
    except (ValueError, TypeError):
        return False


def install_demo_access(app: FastAPI, settings) -> None:
    enabled = settings.demo_access_enabled
    origin = settings.demo_public_origin.rstrip("/")
    if enabled and (len(settings.demo_session_secret) < 32 or not settings.demo_passcode_hash.startswith("scrypt$")
                    or urlsplit(origin).scheme not in {"http", "https"} or not urlsplit(origin).netloc):
        raise ValueError("Hosted demo requires a passcode hash, a session secret of at least 32 characters, and a public origin")
    if enabled and settings.demo_secure_cookies and not origin.startswith("https://"):
        raise ValueError("Secure hosted demo cookies require an HTTPS public origin")
    if enabled:
        for dsn in (settings.read_database_dsn, settings.tribunal_database_dsn):
            name = urlsplit(dsn).path.lstrip("/") if dsn else ""
            if name and name != "ryde_tribunal_demo" and not name.endswith(("_test", "_tests")):
                raise ValueError("Hosted demo must use its own synthetic demo database")
    cookie = "__Host-ryde_session" if settings.demo_secure_cookies else "ryde_session"
    attempts: OrderedDict[str, deque] = OrderedDict()

    def limited(key: str, maximum: int, period: int) -> bool:
        now = time.monotonic()
        values = attempts.setdefault(key, deque())
        attempts.move_to_end(key)
        while values and values[0] <= now - period:
            values.popleft()
        if len(values) >= maximum:
            return True
        values.append(now)
        while len(attempts) > 2048:
            attempts.popitem(last=False)
        return False

    def token(payload: dict) -> str:
        value = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        signature = hmac.new(settings.demo_session_secret.encode(), value.encode(), hashlib.sha256).hexdigest()
        return f"{value}.{signature}"

    def session(request: Request) -> dict | None:
        try:
            value, signature = request.cookies.get(cookie, "").split(".")
            expected = hmac.new(settings.demo_session_secret.encode(), value.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
            return payload if payload["exp"] > time.time() and isinstance(payload["id"], str) else None
        except (ValueError, KeyError, TypeError):
            return None

    def error(code: str, message: str, status: int):
        return JSONResponse({"error": {"code": code, "message": message, "details": {}}}, status_code=status,
                            headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path == "/healthz":
            return JSONResponse({"status": "ok"})
        protected = path.startswith("/api/") or path.startswith(("/docs", "/redoc", "/openapi"))
        if enabled and protected:
            if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("origin") != origin:
                return error("access_denied", "Open the judge workspace to make this change.", 403)
            if path not in {"/api/v1/demo/session", "/api/v1/demo/guest-session"}:
                active = session(request)
                if not active:
                    return error("authentication_required", "Sign in with the judge passcode.", 401)
                if active.get("mode") == "guest" and request.method not in {"GET", "HEAD", "OPTIONS"}:
                    return error("demo_read_only", "Guest profiles are read-only. Your changes are not saved.", 403)
                if path.startswith("/api/v1/imports"):
                    return error("demo_restricted", "Bulk imports are disabled in the shared synthetic demo.", 403)
                if request.method not in {"GET", "HEAD", "OPTIONS"} and limited("write:" + active["id"], 40, 600):
                    return error("rate_limited", "Too many changes. Wait a few minutes and try again.", 429)
                request.scope["headers"] = [(k, v) for k, v in request.scope["headers"] if k.lower() != b"x-reviewer-id"] + [(b"x-reviewer-id", ("demo-" + active["id"]).encode())]
        response = await call_next(request)
        if protected:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/demo/session")
    def current_session(request: Request):
        active = session(request)
        return {"access_required": enabled, "authenticated": bool(active) if enabled else True,
                "mode": (active or {}).get("mode", "reviewer"), "profile": (active or {}).get("profile")}

    @app.post("/api/v1/demo/guest-session")
    async def guest_session(request: Request):
        if not enabled:
            return error("demo_restricted", "Guest profiles are available in the hosted demo.", 404)
        if request.headers.get("origin") != origin:
            return error("access_denied", "Open the demo from its official website.", 403)
        if limited("guest:" + (request.client.host if request.client else "unknown"), 20, 600):
            return error("rate_limited", "Too many guest sessions. Please wait a few minutes.", 429)
        try:
            body = await request.json()
            profile = body.get("profile")
        except (ValueError, AttributeError):
            profile = None
        if profile not in {"reviewer-preview", "evidence-explorer"}:
            return error("validation_error", "Choose one of the available guest profiles.", 422)
        response = JSONResponse({"access_required": True, "authenticated": True, "mode": "guest", "profile": profile})
        response.set_cookie(cookie, token({"id": secrets.token_hex(12), "exp": int(time.time()) + settings.demo_session_hours * 3600,
                                           "mode": "guest", "profile": profile}),
                            max_age=settings.demo_session_hours * 3600, httponly=True, secure=settings.demo_secure_cookies,
                            samesite="lax", path="/")
        return response

    @app.post("/api/v1/demo/session")
    async def login(request: Request):
        if not enabled:
            return {"access_required": False, "authenticated": True}
        host = request.client.host if request.client else "unknown"
        if limited("login:" + host, 8, 600) or limited("login:global", 60, 600):
            return error("rate_limited", "Too many sign-in attempts. Please wait ten minutes.", 429)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1024:
                return error("validation_error", "Enter the supplied judge passcode.", 422)
        try:
            passcode = json.loads(body).get("passcode")
        except (ValueError, AttributeError):
            passcode = None
        if not isinstance(passcode, str) or not 1 <= len(passcode) <= 256 or not verify_passcode(passcode, settings.demo_passcode_hash):
            return error("authentication_required", "That passcode was not recognised.", 401)
        response = JSONResponse({"access_required": True, "authenticated": True, "mode": "reviewer", "profile": "judge-reviewer"})
        response.set_cookie(cookie, token({"id": secrets.token_hex(12), "exp": int(time.time()) + settings.demo_session_hours * 3600,
                                           "mode": "reviewer", "profile": "judge-reviewer"}),
                            max_age=settings.demo_session_hours * 3600, httponly=True, secure=settings.demo_secure_cookies, samesite="lax", path="/")
        return response

    @app.delete("/api/v1/demo/session")
    def logout():
        response = JSONResponse({"access_required": enabled, "authenticated": not enabled})
        response.delete_cookie(cookie, path="/", secure=settings.demo_secure_cookies, httponly=True, samesite="lax")
        return response
