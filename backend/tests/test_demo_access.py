from fastapi.testclient import TestClient
import pytest
from app.api.app import create_app
from app.api.container import build_container
from app.api.demo_access import hash_passcode
from tests.conftest import make_settings
from tests.fixtures.reader import FixtureReader

PASSCODE = "synthetic-test-passcode"
ORIGIN = "https://judge.example.test"


def client(**overrides):
    settings = make_settings(demo_access_enabled=True, demo_public_origin=ORIGIN,
                             demo_passcode_hash=hash_passcode(PASSCODE), demo_session_secret="s" * 40,
                             **overrides)
    return TestClient(create_app(build_container(reader=FixtureReader(), settings=settings)), base_url=ORIGIN)


def login(c):
    return c.post("/api/v1/demo/session", json={"passcode": PASSCODE}, headers={"origin": ORIGIN})


def test_protects_api_evidence_docs_and_forged_reviewer_header():
    c = client()
    for path in ("/api/v1/disputes", "/api/v1/evidence/EV-000001", "/docs", "/openapi.json", "/api/v1/health"):
        assert c.get(path, headers={"X-Reviewer-Id": "forged"}).status_code == 401
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.get("/api/v1/demo/session").json()["authenticated"] is False


def test_secure_session_sign_in_tamper_logout_and_import_restriction():
    c = client()
    response = login(c)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert c.get("/api/v1/demo/session").json()["authenticated"] is True
    assert c.get("/api/v1/disputes").status_code == 200
    assert c.post("/api/v1/imports/company-data", headers={"origin": ORIGIN}).status_code == 403
    assert c.get("/api/v1/disputes").headers["cache-control"] == "no-store"
    assert c.delete("/api/v1/demo/session", headers={"origin": ORIGIN}).status_code == 200
    assert c.get("/api/v1/disputes").status_code == 401
    c.cookies.set("__Host-ryde_session", "tampered.signature")
    assert c.get("/api/v1/disputes").status_code == 401


def test_rejects_cross_origin_missing_origin_large_login_and_throttles_attempts():
    c = client()
    for origin in ("https://attacker.test", "null", ""):
        assert c.post("/api/v1/demo/session", json={"passcode": PASSCODE}, headers={"origin": origin}).status_code == 403
    assert c.post("/api/v1/demo/session", content="a" * 2048, headers={"origin": ORIGIN}).status_code == 422
    for _ in range(7):
        assert c.post("/api/v1/demo/session", json={"passcode": "wrong"}, headers={"origin": ORIGIN}).status_code == 401
    assert login(c).status_code == 429


def test_demo_configuration_fails_closed_for_missing_secret_or_primary_database():
    with pytest.raises(ValueError, match="synthetic demo database"):
        client(read_database_dsn="postgresql:///ryde_tribunal")
    with pytest.raises(ValueError, match="requires a passcode"):
        settings = make_settings(demo_access_enabled=True)
        create_app(build_container(reader=FixtureReader(), settings=settings))
