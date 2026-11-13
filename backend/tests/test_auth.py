from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Flat, User
from app.rate_limit import check_otp_rate_limit, reset_otp_rate_limits


@pytest.fixture
def auth_api():
    reset_otp_rate_limits()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)
    with TestSession() as db:
        flat = Flat(code="T77-0101", tower="T77", area_sqft=900)
        db.add(flat)
        db.flush()
        resident = User(phone="9000000071", name="Resident", role="resident", flat_id=flat.id)
        helpdesk = User(phone="9000000072", name="Helpdesk", role="helpdesk")
        db.add_all([resident, helpdesk])
        db.commit()
        resident_id = resident.id

    def override_get_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, TestSession, resident_id
    finally:
        reset_otp_rate_limits()
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def _resident_token(user_id, expiration):
    return jwt.encode(
        {"sub": str(user_id), "role": "resident", "exp": expiration},
        settings.jwt_secret,
        algorithm="HS256",
    )


def test_valid_login_returns_user_and_role(auth_api):
    client, _, _ = auth_api
    response = client.post("/auth/verify-otp", json={"phone": "9000000071", "otp": "123456"})
    assert response.status_code == 200
    result = response.json()
    assert result["role"] == "resident"
    assert result["user_id"] > 0
    assert result["token_type"] == "bearer"
    assert result["access_token"]


def test_wrong_otp_is_rejected(auth_api):
    client, _, _ = auth_api
    response = client.post("/auth/verify-otp", json={"phone": "9000000071", "otp": "000000"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid phone or OTP"}


def test_unknown_phone_has_same_error_as_wrong_otp(auth_api):
    client, _, _ = auth_api
    response = client.post("/auth/verify-otp", json={"phone": "9999999999", "otp": "123456"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid phone or OTP"}


def test_resident_cannot_access_helpdesk_queue(auth_api):
    client, _, _ = auth_api
    login = client.post("/auth/verify-otp", json={"phone": "9000000071", "otp": "123456"})
    response = client.get(
        "/helpdesk/queue", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert response.status_code == 403


def test_expired_token_returns_401(auth_api):
    client, _, resident_id = auth_api
    token = _resident_token(resident_id, datetime.now(timezone.utc) - timedelta(minutes=1))
    response = client.get("/helpdesk/queue", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_deactivated_users_token_returns_401(auth_api):
    client, Session, resident_id = auth_api
    with Session() as db:
        user = db.get(User, resident_id)
        user.is_active = False
        db.commit()

    token = _resident_token(resident_id, datetime.now(timezone.utc) + timedelta(minutes=5))
    response = client.get("/helpdesk/queue", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_request_otp_is_limited_by_ip(auth_api):
    client, _, _ = auth_api
    for index in range(5):
        response = client.post("/auth/request-otp", json={"phone": f"90000010{index:02d}"})
        assert response.status_code == 200
    response = client.post("/auth/request-otp", json={"phone": "9000001099"})
    assert response.status_code == 429


def test_verify_otp_is_limited_by_phone_and_ip(auth_api):
    client, _, _ = auth_api
    for _ in range(5):
        response = client.post("/auth/verify-otp", json={"phone": "9000000999", "otp": "000000"})
        assert response.status_code == 401
    response = client.post("/auth/verify-otp", json={"phone": "9000000999", "otp": "000000"})
    assert response.status_code == 429


def test_rate_limiter_applies_phone_limit_across_ips():
    reset_otp_rate_limits()
    for index in range(5):
        check_otp_rate_limit("9000000998", f"192.0.2.{index + 1}")
    with pytest.raises(HTTPException) as error:
        check_otp_rate_limit("9000000998", "192.0.2.10")
    assert error.value.status_code == 429
    reset_otp_rate_limits()


def test_every_api_route_has_auth_except_health_and_otp_login():
    from fastapi.routing import APIRoute

    from app.auth import get_current_user

    public_paths = {"/health", "/auth/request-otp", "/auth/verify-otp"}

    def contains_auth(dependant):
        return dependant.call is get_current_user or any(contains_auth(child) for child in dependant.dependencies)

    unprotected = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path not in public_paths
        and not contains_auth(route.dependant)
    ]
    assert unprotected == []


def test_docs_and_schema_require_authentication(auth_api):
    client, _, _ = auth_api
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 401

    login = client.post("/auth/verify-otp", json={"phone": "9000000071", "otp": "123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/docs", headers=headers).status_code == 200
    assert client.get("/openapi.json", headers=headers).status_code == 200
    assert client.get("/redoc", headers=headers, follow_redirects=False).status_code == 307
