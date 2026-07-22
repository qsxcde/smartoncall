from smartoncall.services.auth.schemas import (
    SendCodeRequest,
    RegisterRequest,
    PasswordLoginRequest,
    CodeLoginRequest,
    RefreshRequest,
    TokenResponse,
    MessageResponse,
)


def test_send_code_request():
    req = SendCodeRequest(email="a@b.com")
    assert req.email == "a@b.com"


def test_register_request():
    req = RegisterRequest(email="a@b.com", code="123456", username="test", password="pass123")
    assert req.username == "test"


def test_password_login_request():
    req = PasswordLoginRequest(email="a@b.com", password="pass")
    assert req.email == "a@b.com"


def test_code_login_request():
    req = CodeLoginRequest(email="a@b.com", code="654321")
    assert req.code == "654321"


def test_token_response():
    resp = TokenResponse(access_token="at", refresh_token="rt", token_type="bearer")
    assert resp.token_type == "bearer"


def test_message_response():
    resp = MessageResponse(message="注册成功")
    assert resp.message == "注册成功"
