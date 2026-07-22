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
