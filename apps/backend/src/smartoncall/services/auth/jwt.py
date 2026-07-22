import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from smartoncall.config import get_settings


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: int, email: str) -> str:
    settings = get_settings()
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> tuple[str, str]:
    settings = get_settings()
    jti = str(uuid.uuid4())
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "jti": jti,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    token = pyjwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return pyjwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except pyjwt.PyJWTError:
        raise InvalidTokenError("Token 无效或已过期")
