from fastapi import APIRouter, HTTPException, Request

from smartoncall.services.auth.schemas import (
    CodeLoginRequest,
    MessageResponse,
    PasswordLoginRequest,
    RefreshRequest,
    RegisterRequest,
    SendCodeRequest,
    TokenResponse,
)
from smartoncall.services.auth.service import AuthService

router = APIRouter()


def _get_service(request: Request) -> AuthService:
    return AuthService(db=request.app.state.db_factory(), redis=request.app.state.redis)


@router.post("/register/send-code", response_model=MessageResponse)
async def send_register_code(body: SendCodeRequest, request: Request):
    service = _get_service(request)
    try:
        await service.send_register_code(body.email)
    except ValueError as e:
        raise HTTPException(status_code=_error_status(str(e)), detail=str(e))
    return MessageResponse(message="验证码已发送")


@router.post("/register", response_model=MessageResponse)
async def register(body: RegisterRequest, request: Request):
    service = _get_service(request)
    try:
        await service.register(
            email=body.email, code=body.code, username=body.username, password=body.password
        )
    except ValueError as e:
        raise HTTPException(status_code=_error_status(str(e)), detail=str(e))
    return MessageResponse(message="注册成功")


@router.post("/login/password", response_model=TokenResponse)
async def login_password(body: PasswordLoginRequest, request: Request):
    service = _get_service(request)
    try:
        return await service.login_with_password(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=_error_status(str(e)), detail=str(e))


@router.post("/login/code/send-code", response_model=MessageResponse)
async def send_login_code(body: SendCodeRequest, request: Request):
    service = _get_service(request)
    try:
        await service.send_login_code(body.email)
    except ValueError as e:
        raise HTTPException(status_code=_error_status(str(e)), detail=str(e))
    return MessageResponse(message="验证码已发送")


@router.post("/login/code", response_model=TokenResponse)
async def login_code(body: CodeLoginRequest, request: Request):
    service = _get_service(request)
    try:
        return await service.login_with_code(body.email, body.code)
    except ValueError as e:
        raise HTTPException(status_code=_error_status(str(e)), detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request):
    service = _get_service(request)
    try:
        return await service.refresh_access_token(body.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout", response_model=MessageResponse)
async def logout(body: RefreshRequest, request: Request):
    service = _get_service(request)
    await service.logout(body.refresh_token)
    return MessageResponse(message="已登出")


def _error_status(message: str) -> int:
    mapping = {
        "邮箱格式不正确": 422,
        "该邮箱已注册": 409,
        "请60秒后再试": 429,
        "验证码错误或已过期": 400,
        "邮箱或密码错误": 401,
        "登录尝试过多，请15分钟后再试": 423,
        "账户已被禁用": 403,
        "该邮箱未注册": 400,
    }
    return mapping.get(message, 400)
