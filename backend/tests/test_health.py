from fastapi import FastAPI
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import SecurityHeadersMiddleware, app


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "style-src 'self'" in csp and "font-src 'self'" in csp


def test_unhandled_error_response_is_generic_and_has_security_headers():
    error_app = FastAPI()
    error_app.add_middleware(SecurityHeadersMiddleware)

    @error_app.get("/failure")
    def failure():
        raise RuntimeError("sensitive request details")

    response = TestClient(error_app, raise_server_exceptions=False).get("/failure")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "sensitive request details" not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"


def test_built_frontend_html_uses_self_hosted_assets_when_build_exists():
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if not dist.is_dir():
        return
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "https://" not in response.text
