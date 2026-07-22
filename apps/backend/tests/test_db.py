import pytest

from smartoncall.db.mysql import Base, engine, async_session_factory


def test_base_has_metadata():
    assert Base.metadata is not None


def test_session_factory_is_configured():
    assert async_session_factory is not None


def test_engine_is_configured():
    assert engine is not None
    assert "aiomysql" in str(engine.url)
