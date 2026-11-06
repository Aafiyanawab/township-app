from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])
Phone = Annotated[str, StringConstraints(pattern=r"^\+?[0-9]{7,15}$")]


class OTPRequest(BaseModel):
    phone: Phone


class OTPVerification(BaseModel):
    phone: Phone
    otp: Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


@router.post("/request-otp")
def request_otp(payload: OTPRequest, db: Annotated[Session, Depends(get_db)]):
    # Same response for existing and unknown numbers prevents account discovery.
    db.query(User.id).filter(User.phone == payload.phone, User.is_active.is_(True)).first()
    return {"message": "If the phone number is registered, an OTP has been sent."}


@router.post("/verify-otp")
def verify_otp(payload: OTPVerification, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.phone == payload.phone, User.is_active.is_(True)).first()
    if settings.otp_mode != "mock" or payload.otp != "123456" or user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid phone or OTP")

    token = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer", "user_id": user.id, "role": user.role}
