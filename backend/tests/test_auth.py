from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.main import app

client = TestClient(app)


def test_valid_login_returns_user_and_role():
    response = client.post("/auth/verify-otp", json={"phone": "9000020001", "otp": "123456"})
    assert response.status_code == 200
    result = response.json()
    assert result["role"] == "resident"
    assert result["user_id"] > 0
    assert result["token_type"] == "bearer"
    assert result["access_token"]


def test_wrong_otp_is_rejected():
    response = client.post("/auth/verify-otp", json={"phone": "9000020001", "otp": "000000"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid phone or OTP"}


def test_unknown_phone_has_same_error_as_wrong_otp():
    response = client.post("/auth/verify-otp", json={"phone": "9999999999", "otp": "123456"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid phone or OTP"}


def test_resident_cannot_access_helpdesk_queue():
    login = client.post("/auth/verify-otp", json={"phone": "9000020001", "otp": "123456"})
    response = client.get(
        "/helpdesk/queue", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert response.status_code == 403


def _resident_token(expiration):
    with SessionLocal() as db:
        user = db.query(User).filter_by(phone="9000020001").one()
        user_id, role = user.id, user.role
    return jwt.encode(
        {"sub": str(user_id), "role": role, "exp": expiration},
        settings.jwt_secret,
        algorithm="HS256",
    )


def test_expired_token_returns_401():
    token = _resident_token(datetime.now(timezone.utc) - timedelta(minutes=1))
    response = client.get("/helpdesk/queue", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_deactivated_users_token_returns_401():
    with SessionLocal() as db:
        user = db.query(User).filter_by(phone="9000020001").one()
        user_id = user.id
        user.is_active = False
        db.commit()

    try:
        token = jwt.encode(
            {"sub": str(user_id), "role": "resident", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            settings.jwt_secret,
            algorithm="HS256",
        )
        response = client.get("/helpdesk/queue", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
    finally:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            user.is_active = True
            db.commit()
