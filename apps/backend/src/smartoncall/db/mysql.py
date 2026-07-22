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
