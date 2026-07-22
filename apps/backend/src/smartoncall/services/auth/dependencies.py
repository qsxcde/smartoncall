from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from smartoncall.services.auth.jwt import decode_token, InvalidTokenError

security = HTTPBearer()


def get_db(request: Request):
    return request.app.state.db_factory()


def get_redis_client(request: Request) -> Redis:
    return request.app.state.redis


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    return {"user_id": payload["user_id"], "email": payload["email"]}
