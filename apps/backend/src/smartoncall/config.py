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
