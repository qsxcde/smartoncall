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
