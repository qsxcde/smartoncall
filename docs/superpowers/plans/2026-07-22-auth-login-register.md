# 登录注册功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 实现基于邮箱的用户注册和登录（密码 + 验证码），使用 JWT 令牌，后端由 MySQL 和 Redis 支撑。

**架构：** MySQL 中单张 `users` 表存储持久化数据；Redis 处理所有临时状态（验证码、refresh token、限流、会话缓存）。FastAPI 中间件通过 structlog 注入 request_id 实现可观测性。认证逻辑作为自包含模块位于 `services/auth/`。

**技术栈：** FastAPI, SQLAlchemy 2.0 (async), aiomysql, redis[hiredis], PyJWT, bcrypt, pydantic-settings, structlog

## 全局约束

- Python >= 3.12，包管理使用 `uv`
- 包目录为 `apps/backend/src/smartOncall/`，但 Python 导入使用 `smartoncall`
- 所有日志通过 `structlog.get_logger()` 输出；禁止使用 `print()` 或标准 `logging`
- 日志字段 key 使用英文，event 事件描述使用中文
- 敏感字段（密码、验证码、token）禁止出现在日志中
- 邮箱正则：`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`
- access_token 有效期：15分钟；refresh_token 有效期：7天
- 验证码有效期：300秒；发送间隔：60秒
- 登录锁定：5次失败后锁定900秒
- 源码根目录：`apps/backend/src/smartOncall/`
- 测试根目录：`apps/backend/tests/`
- 运行测试：`cd apps/backend && uv run pytest tests/ -v`
- 运行服务：`cd apps/backend && uv run uvicorn smartoncall.main:app --reload`

---

## 文件结构

```
apps/backend/src/smartOncall/
├── __init__.py
├── main.py                    # FastAPI 应用工厂、生命周期、中间件注册
├── config.py                  # 配置管理（pydantic-settings）
├── logging_config.py          # structlog 配置
├── middleware/
│   ├── __init__.py
│   └── request_context.py     # RequestContextMiddleware（request_id 注入）
├── db/
│   ├── __init__.py
│   ├── mysql.py               # 异步引擎、会话工厂、Base
│   └── redis.py               # Redis 连接池单例
├── models/
│   ├── __init__.py
│   └── user.py                # User ORM 模型
├── services/
│   ├── __init__.py
│   └── auth/
│       ├── __init__.py
│       ├── router.py          # API 端点
│       ├── schemas.py         # Pydantic 请求/响应模型
│       ├── service.py         # 业务逻辑
│       ├── jwt.py             # JWT 签发/验证
│       ├── dependencies.py    # get_current_user 依赖
│       └── validators.py      # 邮箱校验
└── (已有: api/, core/, prompts/, tools/, utils/)

apps/backend/tests/
├── conftest.py                # 共享 fixtures（异步客户端、fake redis、测试数据库）
├── test_validators.py
├── test_jwt.py
├── test_auth_service.py
└── test_auth_api.py
```

---

### 任务 1：依赖与配置管理

**文件：**
- 修改: `apps/backend/pyproject.toml`
- 创建: `apps/backend/src/smartOncall/config.py`
- 创建: `apps/backend/.env`
- 测试: `apps/backend/tests/test_config.py`

**接口：**
- 产出: `get_settings() -> Settings`，供后续所有任务使用

- [ ] **步骤 1：在 pyproject.toml 中添加依赖**

```toml
[project]
name = "smartoncall"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.139.2",
    "langchain>=1.3.14",
    "langchain-openai>=1.4.0",
    "langgraph>=1.2.9",
    "uvicorn>=0.51.0",
    "sqlalchemy[asyncio]>=2.0",
    "aiomysql",
    "redis[hiredis]>=5.0",
    "pyjwt",
    "bcrypt",
    "pydantic-settings",
    "structlog>=24.0",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "httpx",
    "fakeredis",
    "aiosqlite",
]
```

- [ ] **步骤 2：安装依赖**

运行: `cd apps/backend && uv sync --all-extras`
预期: 所有包安装成功

- [ ] **步骤 3：编写失败的测试**

```python
# apps/backend/tests/test_config.py
import os
from unittest.mock import patch


def test_settings_loads_defaults():
    env = {
        "MYSQL_HOST": "localhost",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "test",
        "JWT_SECRET": "test-secret",
    }
    with patch.dict(os.environ, env, clear=False):
        from smartoncall.config import Settings
        s = Settings()
        assert s.MYSQL_PORT == 3306
        assert s.MYSQL_DATABASE == "smartoncall"
        assert s.REDIS_URL == "redis://localhost:6379/0"
        assert s.JWT_ALGORITHM == "HS256"
        assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 15
        assert s.REFRESH_TOKEN_EXPIRE_DAYS == 7
        assert s.VERIFY_CODE_TTL == 300
        assert s.VERIFY_SEND_INTERVAL == 60
        assert s.LOGIN_MAX_ATTEMPTS == 5
        assert s.LOGIN_LOCK_TTL == 900


def test_settings_mysql_dsn():
    env = {
        "MYSQL_HOST": "dbhost",
        "MYSQL_PORT": "3307",
        "MYSQL_USER": "admin",
        "MYSQL_PASSWORD": "pass123",
        "MYSQL_DATABASE": "mydb",
        "JWT_SECRET": "s",
    }
    with patch.dict(os.environ, env, clear=False):
        from smartoncall.config import Settings
        s = Settings()
        assert s.mysql_dsn == "mysql+aiomysql://admin:pass123@dbhost:3307/mydb"
```

- [ ] **步骤 4：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_config.py -v`
预期: 失败 — `ModuleNotFoundError: No module named 'smartoncall.config'`

- [ ] **步骤 5：实现 config.py**

```python
# apps/backend/src/smartOncall/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str = "smartoncall"

    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    VERIFY_CODE_TTL: int = 300
    VERIFY_SEND_INTERVAL: int = 60

    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_TTL: int = 900

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **步骤 6：创建本地开发 .env 文件**

```env
# apps/backend/.env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=smartoncall

REDIS_URL=redis://localhost:6379/0

JWT_SECRET=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

- [ ] **步骤 7：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_config.py -v`
预期: 通过（2 个测试）

- [ ] **步骤 8：提交**

```bash
git add apps/backend/pyproject.toml apps/backend/src/smartOncall/config.py apps/backend/.env apps/backend/tests/test_config.py
git commit -m "feat: 添加依赖和配置管理"
```

---

### 任务 2：Structlog 配置与请求上下文中间件

**文件：**
- 创建: `apps/backend/src/smartOncall/logging_config.py`
- 创建: `apps/backend/src/smartOncall/middleware/__init__.py`
- 创建: `apps/backend/src/smartOncall/middleware/request_context.py`
- 测试: `apps/backend/tests/test_middleware.py`

**接口：**
- 产出: `setup_logging()` 在应用启动时调用
- 产出: `RequestContextMiddleware` 注册到 FastAPI 应用

- [ ] **步骤 1：编写失败的测试**

```python
# apps/backend/tests/test_middleware.py
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from smartoncall.middleware.request_context import RequestContextMiddleware
from smartoncall.logging_config import setup_logging


@pytest.fixture(autouse=True)
def _setup_logging():
    setup_logging()


@pytest.fixture
def app():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_response_contains_request_id(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/test")
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) == 36  # UUID 格式


@pytest.mark.asyncio
async def test_preserves_incoming_request_id(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/test", headers={"X-Request-ID": "my-custom-id"})
    assert resp.headers["x-request-id"] == "my-custom-id"
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_middleware.py -v`
预期: 失败 — `ModuleNotFoundError`

- [ ] **步骤 3：实现 logging_config.py**

```python
# apps/backend/src/smartOncall/logging_config.py
import logging

import structlog


def setup_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
```

- [ ] **步骤 4：实现 middleware/request_context.py**

```python
# apps/backend/src/smartOncall/middleware/__init__.py
```

```python
# apps/backend/src/smartOncall/middleware/request_context.py
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

- [ ] **步骤 5：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_middleware.py -v`
预期: 通过（2 个测试）

- [ ] **步骤 6：提交**

```bash
git add apps/backend/src/smartOncall/logging_config.py apps/backend/src/smartOncall/middleware/ apps/backend/tests/test_middleware.py
git commit -m "feat: 添加 structlog 配置和请求上下文中间件"
```

---

### 任务 3：数据库层（MySQL + Redis）

**文件：**
- 创建: `apps/backend/src/smartOncall/db/__init__.py`
- 创建: `apps/backend/src/smartOncall/db/mysql.py`
- 创建: `apps/backend/src/smartOncall/db/redis.py`
- 测试: `apps/backend/tests/test_db.py`

**接口：**
- 产出: `Base`（ORM 模型的声明式基类）
- 产出: `get_db_session() -> AsyncGenerator[AsyncSession]`（FastAPI 依赖）
- 产出: `get_redis() -> Redis`（FastAPI 依赖）

- [ ] **步骤 1：编写失败的测试**

```python
# apps/backend/tests/test_db.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from smartoncall.db.mysql import Base, engine, async_session_factory


def test_base_has_metadata():
    assert Base.metadata is not None


@pytest.mark.asyncio
async def test_session_factory_creates_session():
    async with async_session_factory() as session:
        assert isinstance(session, AsyncSession)
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_db.py -v`
预期: 失败 — `ModuleNotFoundError`

- [ ] **步骤 3：实现 db/mysql.py**

```python
# apps/backend/src/smartOncall/db/__init__.py
```

```python
# apps/backend/src/smartOncall/db/mysql.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from smartoncall.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.mysql_dsn, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db_session():
    async with async_session_factory() as session:
        yield session
```

- [ ] **步骤 4：实现 db/redis.py**

```python
# apps/backend/src/smartOncall/db/redis.py
import redis.asyncio as aioredis

from smartoncall.config import get_settings

settings = get_settings()

redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global redis_client
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis 未初始化，请先调用 init_redis()")
    return redis_client
```

- [ ] **步骤 5：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_db.py -v`
预期: 通过（2 个测试）

注意：如果本地 MySQL 未运行，session factory 测试可能因连接失败。此时可调整为仅验证工厂已配置：

```python
@pytest.mark.asyncio
async def test_session_factory_is_configured():
    assert async_session_factory is not None
```

- [ ] **步骤 6：提交**

```bash
git add apps/backend/src/smartOncall/db/ apps/backend/tests/test_db.py
git commit -m "feat: 添加异步 MySQL 和 Redis 数据库层"
```

---

### 任务 4：User ORM 模型

**文件：**
- 创建: `apps/backend/src/smartOncall/models/user.py`
- 修改: `apps/backend/src/smartOncall/models/__init__.py`
- 测试: `apps/backend/tests/test_user_model.py`

**接口：**
- 产出: `User` 模型，字段：id, email, username, password_hash, is_active, created_at, updated_at
- 消费: `smartoncall.db.mysql` 中的 `Base`

- [ ] **步骤 1：编写失败的测试**

```python
# apps/backend/tests/test_user_model.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smartoncall.db.mysql import Base
from smartoncall.models.user import User


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(email="test@example.com", username="tester", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.username == "tester"
    assert user.is_active is True


@pytest.mark.asyncio
async def test_email_unique_constraint(db_session):
    user1 = User(email="dup@example.com", username="u1", password_hash="h1")
    db_session.add(user1)
    await db_session.commit()

    user2 = User(email="dup@example.com", username="u2", password_hash="h2")
    db_session.add(user2)
    with pytest.raises(Exception):
        await db_session.commit()
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_user_model.py -v`
预期: 失败 — `ModuleNotFoundError: No module named 'smartoncall.models.user'`

- [ ] **步骤 3：实现 models/user.py**

```python
# apps/backend/src/smartOncall/models/user.py
from datetime import datetime

from sqlalchemy import String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from smartoncall.db.mysql import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

- [ ] **步骤 4：更新 models/__init__.py**

```python
# apps/backend/src/smartOncall/models/__init__.py
from smartoncall.models.user import User

__all__ = ["User"]
```

- [ ] **步骤 5：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_user_model.py -v`
预期: 通过（2 个测试）

- [ ] **步骤 6：提交**

```bash
git add apps/backend/src/smartOncall/models/ apps/backend/tests/test_user_model.py
git commit -m "feat: 添加 User ORM 模型"
```

---

### 任务 5：邮箱校验器

**文件：**
- 创建: `apps/backend/src/smartOncall/services/auth/__init__.py`
- 创建: `apps/backend/src/smartOncall/services/auth/validators.py`
- 测试: `apps/backend/tests/test_validators.py`

**接口：**
- 产出: `validate_email(email: str) -> bool`
- 产出: `EMAIL_REGEX` 正则常量

- [ ] **步骤 1：编写失败的测试**

```python
# apps/backend/tests/test_validators.py
import pytest

from smartoncall.services.auth.validators import validate_email


@pytest.mark.parametrize("email", [
    "user@example.com",
    "user.name@example.com",
    "user+tag@example.co.uk",
    "user123@sub.domain.org",
    "a@b.cc",
])
def test_valid_emails(email):
    assert validate_email(email) is True


@pytest.mark.parametrize("email", [
    "",
    "plaintext",
    "@example.com",
    "user@",
    "user@.com",
    "user@com",
    "user @example.com",
    "user@@example.com",
    "user@example",
])
def test_invalid_emails(email):
    assert validate_email(email) is False
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_validators.py -v`
预期: 失败 — `ModuleNotFoundError`

- [ ] **步骤 3：实现 validators.py**

```python
# apps/backend/src/smartOncall/services/auth/__init__.py
```

```python
# apps/backend/src/smartOncall/services/auth/validators.py
import re

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email))
```

- [ ] **步骤 4：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_validators.py -v`
预期: 通过（14 个测试）

- [ ] **步骤 5：提交**

```bash
git add apps/backend/src/smartOncall/services/auth/__init__.py apps/backend/src/smartOncall/services/auth/validators.py apps/backend/tests/test_validators.py
git commit -m "feat: 添加邮箱校验器"
```

---

### 任务 6：JWT 工具

**文件：**
- 创建: `apps/backend/src/smartOncall/services/auth/jwt.py`
- 测试: `apps/backend/tests/test_jwt.py`

**接口：**
- 产出: `create_access_token(user_id: int, email: str) -> str`
- 产出: `create_refresh_token(user_id: int) -> tuple[str, str]`（token, jti）
- 产出: `decode_token(token: str) -> dict`（失败抛出 `InvalidTokenError`）
- 消费: `smartoncall.config` 中的 `Settings`

- [ ] **步骤 1：编写失败的测试**

```python
# apps/backend/tests/test_jwt.py
import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    env = {
        "MYSQL_HOST": "localhost",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "test",
        "JWT_SECRET": "test-secret-key",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from smartoncall.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_jwt.py -v`
预期: 失败 — `ModuleNotFoundError`

- [ ] **步骤 3：实现 jwt.py**

```python
# apps/backend/src/smartOncall/services/auth/jwt.py
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
```

- [ ] **步骤 4：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_jwt.py -v`
预期: 通过（4 个测试）

- [ ] **步骤 5：提交**

```bash
git add apps/backend/src/smartOncall/services/auth/jwt.py apps/backend/tests/test_jwt.py
git commit -m "feat: 添加 JWT 签发/验证工具"
```

---

### 任务 7：认证 Pydantic 模型

**文件：**
- 创建: `apps/backend/src/smartOncall/services/auth/schemas.py`
- 测试: `apps/backend/tests/test_schemas.py`

**接口：**
- 产出: `SendCodeRequest`, `RegisterRequest`, `PasswordLoginRequest`, `CodeLoginRequest`, `RefreshRequest`, `TokenResponse`, `MessageResponse`

- [ ] **步骤 1：编写失败的测试**

```python
# apps/backend/tests/test_schemas.py
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
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_schemas.py -v`
预期: 失败 — `ModuleNotFoundError`

- [ ] **步骤 3：实现 schemas.py**

```python
# apps/backend/src/smartOncall/services/auth/schemas.py
from pydantic import BaseModel


class SendCodeRequest(BaseModel):
    email: str


class RegisterRequest(BaseModel):
    email: str
    code: str
    username: str
    password: str


class PasswordLoginRequest(BaseModel):
    email: str
    password: str


class CodeLoginRequest(BaseModel):
    email: str
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str
```

- [ ] **步骤 4：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_schemas.py -v`
预期: 通过（6 个测试）

- [ ] **步骤 5：提交**

```bash
git add apps/backend/src/smartOncall/services/auth/schemas.py apps/backend/tests/test_schemas.py
git commit -m "feat: 添加认证 Pydantic 模型"
```

---

### 任务 8：认证服务 — 注册

**文件：**
- 创建: `apps/backend/src/smartOncall/services/auth/service.py`
- 测试: `apps/backend/tests/test_auth_service.py`

**接口：**
- 产出: `AuthService` 类，方法：`send_register_code`, `register`
- 消费: `AsyncSession`（数据库）, `Redis`（缓存）, `validate_email`, `User` 模型

- [ ] **步骤 1：编写失败的测试**

```python
# apps/backend/tests/test_auth_service.py
import pytest
import fakeredis.aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smartoncall.db.mysql import Base
from smartoncall.models.user import User
from smartoncall.services.auth.service import AuthService


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def redis_client():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def auth_service(db_session, redis_client):
    return AuthService(db=db_session, redis=redis_client)


@pytest.mark.asyncio
async def test_send_register_code_success(auth_service, redis_client):
    await auth_service.send_register_code("new@example.com")
    code = await redis_client.get("verify_code:new@example.com")
    assert code is not None
    assert len(code) == 6


@pytest.mark.asyncio
async def test_send_register_code_invalid_email(auth_service):
    with pytest.raises(ValueError, match="邮箱格式不正确"):
        await auth_service.send_register_code("bad-email")


@pytest.mark.asyncio
async def test_send_register_code_already_registered(auth_service, db_session):
    user = User(email="existing@example.com", username="u", password_hash="h")
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(ValueError, match="该邮箱已注册"):
        await auth_service.send_register_code("existing@example.com")


@pytest.mark.asyncio
async def test_send_register_code_rate_limited(auth_service, redis_client):
    await redis_client.set("verify_limit:rate@example.com", "1", ex=60)
    with pytest.raises(ValueError, match="请60秒后再试"):
        await auth_service.send_register_code("rate@example.com")


@pytest.mark.asyncio
async def test_register_success(auth_service, redis_client, db_session):
    await redis_client.set("verify_code:reg@example.com", "123456", ex=300)
    await auth_service.register(
        email="reg@example.com", code="123456", username="newuser", password="pass123"
    )
    from sqlalchemy import select
    result = await db_session.execute(select(User).where(User.email == "reg@example.com"))
    user = result.scalar_one()
    assert user.username == "newuser"
    assert user.password_hash != "pass123"  # 已哈希


@pytest.mark.asyncio
async def test_register_wrong_code(auth_service, redis_client):
    await redis_client.set("verify_code:reg2@example.com", "111111", ex=300)
    with pytest.raises(ValueError, match="验证码错误或已过期"):
        await auth_service.register(
            email="reg2@example.com", code="999999", username="u", password="p"
        )


@pytest.mark.asyncio
async def test_register_code_deleted_after_use(auth_service, redis_client):
    await redis_client.set("verify_code:reg3@example.com", "123456", ex=300)
    await auth_service.register(
        email="reg3@example.com", code="123456", username="u", password="p"
    )
    code = await redis_client.get("verify_code:reg3@example.com")
    assert code is None
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_auth_service.py -v`
预期: 失败 — `ModuleNotFoundError`

- [ ] **步骤 3：实现 service.py（注册部分）**

```python
# apps/backend/src/smartOncall/services/auth/service.py
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
```

- [ ] **步骤 4：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_auth_service.py -v`
预期: 通过（7 个测试）

- [ ] **步骤 5：提交**

```bash
git add apps/backend/src/smartOncall/services/auth/service.py apps/backend/tests/test_auth_service.py
git commit -m "feat: 实现注册逻辑"
```

---

### 任务 9：认证服务 — 密码登录 + 限流

**文件：**
- 修改: `apps/backend/src/smartOncall/services/auth/service.py`
- 修改: `apps/backend/tests/test_auth_service.py`

**接口：**
- 产出: `AuthService.login_with_password(email, password) -> TokenResponse`
- 消费: `jwt.py` 中的 `create_access_token`, `create_refresh_token`

- [ ] **步骤 1：编写失败的测试（追加到 test_auth_service.py）**

```python
# 追加到 apps/backend/tests/test_auth_service.py
import bcrypt


@pytest.mark.asyncio
async def test_login_with_password_success(auth_service, db_session, redis_client):
    password_hash = bcrypt.hashpw("correct".encode(), bcrypt.gensalt()).decode()
    user = User(email="login@example.com", username="u", password_hash=password_hash)
    db_session.add(user)
    await db_session.commit()

    from smartoncall.services.auth.schemas import TokenResponse
    tokens = await auth_service.login_with_password("login@example.com", "correct")
    assert isinstance(tokens, TokenResponse)
    assert tokens.access_token
    assert tokens.refresh_token

    from smartoncall.services.auth.jwt import decode_token
    payload = decode_token(tokens.refresh_token)
    key = f"refresh_token:{payload['user_id']}:{payload['jti']}"
    assert await redis_client.exists(key)


@pytest.mark.asyncio
async def test_login_with_password_wrong(auth_service, db_session, redis_client):
    password_hash = bcrypt.hashpw("correct".encode(), bcrypt.gensalt()).decode()
    user = User(email="fail@example.com", username="u", password_hash=password_hash)
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(ValueError, match="邮箱或密码错误"):
        await auth_service.login_with_password("fail@example.com", "wrong")

    count = await redis_client.get("login_fail:fail@example.com")
    assert count == "1"


@pytest.mark.asyncio
async def test_login_locked_after_max_attempts(auth_service, db_session, redis_client):
    password_hash = bcrypt.hashpw("correct".encode(), bcrypt.gensalt()).decode()
    user = User(email="locked@example.com", username="u", password_hash=password_hash)
    db_session.add(user)
    await db_session.commit()

    await redis_client.set("login_fail:locked@example.com", "5", ex=900)

    with pytest.raises(ValueError, match="登录尝试过多，请15分钟后再试"):
        await auth_service.login_with_password("locked@example.com", "correct")


@pytest.mark.asyncio
async def test_login_inactive_user(auth_service, db_session):
    password_hash = bcrypt.hashpw("pass".encode(), bcrypt.gensalt()).decode()
    user = User(email="inactive@example.com", username="u", password_hash=password_hash, is_active=False)
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(ValueError, match="账户已被禁用"):
        await auth_service.login_with_password("inactive@example.com", "pass")
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_auth_service.py::test_login_with_password_success -v`
预期: 失败 — `AttributeError: 'AuthService' object has no attribute 'login_with_password'`

- [ ] **步骤 3：在 service.py 中实现 login_with_password**

在 `AuthService` 类中添加：

```python
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
```

- [ ] **步骤 4：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_auth_service.py -v`
预期: 通过（11 个测试）

- [ ] **步骤 5：提交**

```bash
git add apps/backend/src/smartOncall/services/auth/service.py apps/backend/tests/test_auth_service.py
git commit -m "feat: 实现密码登录和限流"
```

---

### 任务 10：认证服务 — 验证码登录、Token 刷新、登出

**文件：**
- 修改: `apps/backend/src/smartOncall/services/auth/service.py`
- 修改: `apps/backend/tests/test_auth_service.py`

**接口：**
- 产出: `AuthService.send_login_code(email)`, `AuthService.login_with_code(email, code) -> TokenResponse`
- 产出: `AuthService.refresh_access_token(refresh_token) -> TokenResponse`
- 产出: `AuthService.logout(refresh_token) -> None`

- [ ] **步骤 1：编写失败的测试（追加到 test_auth_service.py）**

```python
# 追加到 apps/backend/tests/test_auth_service.py

@pytest.mark.asyncio
async def test_send_login_code_success(auth_service, db_session, redis_client):
    user = User(email="code@example.com", username="u", password_hash="h")
    db_session.add(user)
    await db_session.commit()

    await auth_service.send_login_code("code@example.com")
    code = await redis_client.get("verify_code:code@example.com")
    assert code is not None


@pytest.mark.asyncio
async def test_send_login_code_unregistered(auth_service):
    with pytest.raises(ValueError, match="该邮箱未注册"):
        await auth_service.send_login_code("nobody@example.com")


@pytest.mark.asyncio
async def test_login_with_code_success(auth_service, db_session, redis_client):
    user = User(email="codelogin@example.com", username="u", password_hash="h")
    db_session.add(user)
    await db_session.commit()

    await redis_client.set("verify_code:codelogin@example.com", "123456", ex=300)
    tokens = await auth_service.login_with_code("codelogin@example.com", "123456")
    assert tokens.access_token
    assert tokens.refresh_token


@pytest.mark.asyncio
async def test_login_with_code_wrong(auth_service, db_session, redis_client):
    user = User(email="codefail@example.com", username="u", password_hash="h")
    db_session.add(user)
    await db_session.commit()

    await redis_client.set("verify_code:codefail@example.com", "111111", ex=300)
    with pytest.raises(ValueError, match="验证码错误或已过期"):
        await auth_service.login_with_code("codefail@example.com", "999999")


@pytest.mark.asyncio
async def test_refresh_token_success(auth_service, db_session, redis_client):
    user = User(email="refresh@example.com", username="u", password_hash="h")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    from smartoncall.services.auth.jwt import create_refresh_token
    token, jti = create_refresh_token(user_id=user.id)
    await redis_client.set(f"refresh_token:{user.id}:{jti}", "1", ex=604800)

    new_tokens = await auth_service.refresh_access_token(token)
    assert new_tokens.access_token


@pytest.mark.asyncio
async def test_refresh_token_revoked(auth_service, redis_client):
    from smartoncall.services.auth.jwt import create_refresh_token
    token, jti = create_refresh_token(user_id=999)
    with pytest.raises(ValueError, match="登录已过期，请重新登录"):
        await auth_service.refresh_access_token(token)


@pytest.mark.asyncio
async def test_logout(auth_service, db_session, redis_client):
    user = User(email="logout@example.com", username="u", password_hash="h")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    from smartoncall.services.auth.jwt import create_refresh_token
    token, jti = create_refresh_token(user_id=user.id)
    await redis_client.set(f"refresh_token:{user.id}:{jti}", "1", ex=604800)

    await auth_service.logout(token)
    assert not await redis_client.exists(f"refresh_token:{user.id}:{jti}")
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_auth_service.py::test_send_login_code_success -v`
预期: 失败 — `AttributeError`

- [ ] **步骤 3：实现剩余服务方法**

在 `AuthService` 类中添加：

```python
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
```

- [ ] **步骤 4：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_auth_service.py -v`
预期: 通过（18 个测试）

- [ ] **步骤 5：提交**

```bash
git add apps/backend/src/smartOncall/services/auth/service.py apps/backend/tests/test_auth_service.py
git commit -m "feat: 实现验证码登录、Token 刷新和登出"
```

---

### 任务 11：认证路由与依赖注入

**文件：**
- 创建: `apps/backend/src/smartOncall/services/auth/router.py`
- 创建: `apps/backend/src/smartOncall/services/auth/dependencies.py`
- 测试: `apps/backend/tests/test_auth_api.py`

**接口：**
- 产出: FastAPI `APIRouter`，端点：POST `/auth/register/send-code`, POST `/auth/register`, POST `/auth/login/password`, POST `/auth/login/code/send-code`, POST `/auth/login/code`, POST `/auth/refresh`, POST `/auth/logout`
- 产出: `get_current_user` 依赖，从 Bearer token 中提取用户信息

- [ ] **步骤 1：编写失败的测试**

```python
# apps/backend/tests/test_auth_api.py
import pytest
import fakeredis.aioredis
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smartoncall.db.mysql import Base
from smartoncall.services.auth.router import router as auth_router


@pytest.fixture
async def app_with_db():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.state.db_factory = factory
    app.state.redis = fake_redis

    yield app, factory, fake_redis
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_flow(app_with_db):
    app, factory, fake_redis = app_with_db

    await fake_redis.set("verify_code:api@example.com", "123456", ex=300)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/register", json={
            "email": "api@example.com",
            "code": "123456",
            "username": "apiuser",
            "password": "pass123",
        })
    assert resp.status_code == 200
    assert resp.json()["message"] == "注册成功"


@pytest.mark.asyncio
async def test_register_invalid_email(app_with_db):
    app, factory, fake_redis = app_with_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/register/send-code", json={"email": "bad"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_password_flow(app_with_db):
    app, factory, fake_redis = app_with_db

    import bcrypt
    from smartoncall.models.user import User
    async with factory() as session:
        pw_hash = bcrypt.hashpw("pass".encode(), bcrypt.gensalt()).decode()
        session.add(User(email="pw@example.com", username="u", password_hash=pw_hash))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/login/password", json={
            "email": "pw@example.com",
            "password": "pass",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
```

- [ ] **步骤 2：运行测试确认失败**

运行: `cd apps/backend && uv run pytest tests/test_auth_api.py -v`
预期: 失败 — `ModuleNotFoundError`

- [ ] **步骤 3：实现 dependencies.py**

```python
# apps/backend/src/smartOncall/services/auth/dependencies.py
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
```

- [ ] **步骤 4：实现 router.py**

```python
# apps/backend/src/smartOncall/services/auth/router.py
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
```

- [ ] **步骤 5：运行测试确认通过**

运行: `cd apps/backend && uv run pytest tests/test_auth_api.py -v`
预期: 通过（3 个测试）

- [ ] **步骤 6：提交**

```bash
git add apps/backend/src/smartOncall/services/auth/router.py apps/backend/src/smartOncall/services/auth/dependencies.py apps/backend/tests/test_auth_api.py
git commit -m "feat: 添加认证 API 路由和依赖注入"
```

---

### 任务 12：组装 main.py

**文件：**
- 修改: `apps/backend/src/smartOncall/main.py`

**接口：**
- 消费: `setup_logging`, `RequestContextMiddleware`, `init_redis`, `close_redis`, `auth_router`
- 产出: 完整配置的 FastAPI 应用

- [ ] **步骤 1：实现 main.py**

```python
# apps/backend/src/smartOncall/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from smartoncall.db.mysql import engine, Base
from smartoncall.db.redis import init_redis, close_redis
from smartoncall.logging_config import setup_logging
from smartoncall.middleware.request_context import RequestContextMiddleware
from smartoncall.services.auth.router import router as auth_router

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_redis()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(title="SmartOncall", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.include_router(auth_router, prefix="/auth")


@app.get("/")
async def root():
    return {"message": "SmartOncall API"}
```

- [ ] **步骤 2：验证应用可启动（需要 MySQL 和 Redis 运行中）**

运行: `cd apps/backend && uv run uvicorn smartoncall.main:app --reload`
预期: `Uvicorn running on http://127.0.0.1:8000`

如果 MySQL/Redis 不可用，验证导入正确性：
运行: `cd apps/backend && uv run python -c "from smartoncall.main import app; print('OK')"`
预期: `OK`（如果环境变量缺失可能失败 — 先设置 .env）

- [ ] **步骤 3：提交**

```bash
git add apps/backend/src/smartOncall/main.py
git commit -m "feat: 组装 main.py，集成认证路由、中间件和生命周期"
```

---

### 任务 13：更新 .env.example 并最终集成检查

**文件：**
- 修改: `apps/backend/.env.example`

**接口：**
- 无（文档任务）

- [ ] **步骤 1：更新 .env.example**

```env
# apps/backend/.env.example

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=smartoncall

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET=change-me-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# 验证码
VERIFY_CODE_TTL=300
VERIFY_SEND_INTERVAL=60

# 登录限流
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCK_TTL=900

# LLM
LLM_KEY=
LLM_NAME=
LLM_URL=
LLM_TEMPERATURE=
```

- [ ] **步骤 2：运行完整测试套件**

运行: `cd apps/backend && uv run pytest tests/ -v`
预期: 所有测试通过

- [ ] **步骤 3：提交**

```bash
git add apps/backend/.env.example
git commit -m "docs: 更新 .env.example 包含所有配置项"
```
