import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smartoncall.db.mysql import Base
from smartoncall.models.user import User


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
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
