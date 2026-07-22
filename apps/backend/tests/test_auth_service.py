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
    assert user.password_hash != "pass123"


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
