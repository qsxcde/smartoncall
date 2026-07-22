import random
import string

import bcrypt
import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartoncall.config import get_settings
from smartoncall.models.user import User
from smartoncall.services.auth.validators import validate_email

logger = structlog.get_logger()


class AuthService:
    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis
        self.settings = get_settings()

    async def send_register_code(self, email: str) -> None:
        if not validate_email(email):
            raise ValueError("邮箱格式不正确")

        result = await self.db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none() is not None:
            raise ValueError("该邮箱已注册")

        limit_key = f"verify_limit:{email}"
        if await self.redis.exists(limit_key):
            raise ValueError("请60秒后再试")

        code = "".join(random.choices(string.digits, k=6))
        await self.redis.set(f"verify_code:{email}", code, ex=self.settings.VERIFY_CODE_TTL)
        await self.redis.set(limit_key, "1", ex=self.settings.VERIFY_SEND_INTERVAL)

        logger.info("验证码已发送", email=email)

    async def register(self, email: str, code: str, username: str, password: str) -> None:
        if not validate_email(email):
            raise ValueError("邮箱格式不正确")

        stored_code = await self.redis.get(f"verify_code:{email}")
        if stored_code is None or stored_code != code:
            raise ValueError("验证码错误或已过期")

        await self.redis.delete(f"verify_code:{email}")

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(email=email, username=username, password_hash=password_hash)
        self.db.add(user)
        await self.db.commit()

        logger.info("注册成功", email=email, username=username)

    async def login_with_password(self, email: str, password: str) -> "TokenResponse":
        from smartoncall.services.auth.schemas import TokenResponse
        from smartoncall.services.auth.jwt import create_access_token, create_refresh_token

        fail_key = f"login_fail:{email}"
        fail_count = await self.redis.get(fail_key)
        if fail_count and int(fail_count) >= self.settings.LOGIN_MAX_ATTEMPTS:
            raise ValueError("登录尝试过多，请15分钟后再试")

        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            await self.redis.incr(fail_key)
            await self.redis.expire(fail_key, self.settings.LOGIN_LOCK_TTL)
            logger.warning("登录失败，用户不存在", email=email)
            raise ValueError("邮箱或密码错误")

        if not user.is_active:
            raise ValueError("账户已被禁用")

        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            await self.redis.incr(fail_key)
            await self.redis.expire(fail_key, self.settings.LOGIN_LOCK_TTL)
            logger.warning("登录失败，密码错误", email=email)
            raise ValueError("邮箱或密码错误")

        await self.redis.delete(fail_key)

        access_token = create_access_token(user_id=user.id, email=user.email)
        refresh_token, jti = create_refresh_token(user_id=user.id)

        refresh_key = f"refresh_token:{user.id}:{jti}"
        await self.redis.set(
            refresh_key,
            "1",
            ex=self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )

        logger.info("登录成功", user_id=user.id, email=user.email)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def send_login_code(self, email: str) -> None:
        if not validate_email(email):
            raise ValueError("邮箱格式不正确")

        result = await self.db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none() is None:
            raise ValueError("该邮箱未注册")

        limit_key = f"verify_limit:{email}"
        if await self.redis.exists(limit_key):
            raise ValueError("请60秒后再试")

        code = "".join(random.choices(string.digits, k=6))
        await self.redis.set(f"verify_code:{email}", code, ex=self.settings.VERIFY_CODE_TTL)
        await self.redis.set(limit_key, "1", ex=self.settings.VERIFY_SEND_INTERVAL)

        logger.info("验证码已发送", email=email)

    async def login_with_code(self, email: str, code: str) -> "TokenResponse":
        from smartoncall.services.auth.schemas import TokenResponse
        from smartoncall.services.auth.jwt import create_access_token, create_refresh_token

        if not validate_email(email):
            raise ValueError("邮箱格式不正确")

        stored_code = await self.redis.get(f"verify_code:{email}")
        if stored_code is None or stored_code != code:
            raise ValueError("验证码错误或已过期")

        await self.redis.delete(f"verify_code:{email}")

        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one()

        if not user.is_active:
            raise ValueError("账户已被禁用")

        access_token = create_access_token(user_id=user.id, email=user.email)
        refresh_token, jti = create_refresh_token(user_id=user.id)

        await self.redis.set(
            f"refresh_token:{user.id}:{jti}",
            "1",
            ex=self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )

        logger.info("登录成功", user_id=user.id, email=user.email)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def refresh_access_token(self, refresh_token: str) -> "TokenResponse":
        from smartoncall.services.auth.schemas import TokenResponse
        from smartoncall.services.auth.jwt import decode_token, create_access_token, InvalidTokenError

        try:
            payload = decode_token(refresh_token)
        except InvalidTokenError:
            raise ValueError("登录已过期，请重新登录")

        if payload.get("type") != "refresh":
            raise ValueError("登录已过期，请重新登录")

        user_id = payload["user_id"]
        jti = payload["jti"]
        refresh_key = f"refresh_token:{user_id}:{jti}"

        if not await self.redis.exists(refresh_key):
            raise ValueError("登录已过期，请重新登录")

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise ValueError("登录已过期，请重新登录")

        access_token = create_access_token(user_id=user.id, email=user.email)
        logger.info("Token刷新", user_id=user.id)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def logout(self, refresh_token: str) -> None:
        from smartoncall.services.auth.jwt import decode_token, InvalidTokenError

        try:
            payload = decode_token(refresh_token)
        except InvalidTokenError:
            return

        user_id = payload.get("user_id")
        jti = payload.get("jti")
        if user_id and jti:
            await self.redis.delete(f"refresh_token:{user_id}:{jti}")
            logger.info("登出", user_id=user_id)
