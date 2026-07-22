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
