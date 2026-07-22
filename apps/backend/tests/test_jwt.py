import pytest


def test_create_and_decode_access_token():
    from smartoncall.services.auth.jwt import create_access_token, decode_token
    token = create_access_token(user_id=1, email="a@b.com")
    payload = decode_token(token)
    assert payload["user_id"] == 1
    assert payload["email"] == "a@b.com"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    from smartoncall.services.auth.jwt import create_refresh_token, decode_token
    token, jti = create_refresh_token(user_id=42)
    payload = decode_token(token)
    assert payload["user_id"] == 42
    assert payload["type"] == "refresh"
    assert payload["jti"] == jti


def test_decode_invalid_token():
    from smartoncall.services.auth.jwt import decode_token, InvalidTokenError
    with pytest.raises(InvalidTokenError):
        decode_token("invalid.token.here")


def test_decode_expired_token():
    import jwt as pyjwt
    from smartoncall.services.auth.jwt import decode_token, InvalidTokenError
    from smartoncall.config import get_settings
    settings = get_settings()
    expired = pyjwt.encode(
        {"user_id": 1, "type": "access", "exp": 0},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_token(expired)
