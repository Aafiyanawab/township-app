from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Flat, User


@pytest.fixture
def auth_api():
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
