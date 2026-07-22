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
