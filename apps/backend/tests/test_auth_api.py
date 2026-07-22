import pytest
import bcrypt
import fakeredis.aioredis
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smartoncall.db.mysql import Base
from smartoncall.models.user import User
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
