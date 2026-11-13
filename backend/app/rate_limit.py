"""Process-local rate limit for OTP endpoints."""
from collections import deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException

ATTEMPTS_PER_MINUTE = 5
WINDOW_SECONDS = 60.0
_attempts: dict[tuple[str, str], deque[float]] = {}
_lock = Lock()


def check_otp_rate_limit(phone: str, client_ip: str | None) -> None:
    now = monotonic()
    normalized_phone = "".join(character for character in phone if character.isdigit())
    keys = (("phone", normalized_phone), ("ip", client_ip or "unknown"))
    with _lock:
        for key in list(_attempts):
            history = _attempts[key]
            while history and now - history[0] >= WINDOW_SECONDS:
                history.popleft()
            if not history:
                del _attempts[key]

        if any(len(_attempts.get(key, ())) >= ATTEMPTS_PER_MINUTE for key in keys):
            raise HTTPException(status_code=429, detail="Too many OTP attempts. Try again later.")
        for key in keys:
            _attempts.setdefault(key, deque()).append(now)


def reset_otp_rate_limits() -> None:
    """Clear process-local counters for isolated tests."""
    with _lock:
        _attempts.clear()
