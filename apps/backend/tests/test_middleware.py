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
    assert len(resp.headers["x-request-id"]) == 36


@pytest.mark.asyncio
async def test_preserves_incoming_request_id(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/test", headers={"X-Request-ID": "my-custom-id"})
    assert resp.headers["x-request-id"] == "my-custom-id"
