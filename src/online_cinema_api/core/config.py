import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BASE_DIR / ".env"


class BaseAppSettings(BaseSettings):
    app_name: str = "Online Cinema API"
    app_env: str = "development"
    debug: bool = True
    database_url: str

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseAppSettings):
    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY_ACCESS: str = os.getenv("SECRET_KEY_ACCESS", os.urandom(32).hex())
    SECRET_KEY_REFRESH: str = os.getenv("SECRET_KEY_REFRESH", os.urandom(32).hex())
    JWT_SIGNING_ALGORITHM: str = os.getenv("JWT_SIGNING_ALGORITHM", "HS256")

    EMAIL_HOST: str = os.getenv("EMAIL_HOST", "host")
    EMAIL_PORT: int = int(os.getenv("EMAIL_PORT", "25"))
    EMAIL_HOST_USER: str = os.getenv("EMAIL_HOST_USER", "testuser")
    EMAIL_HOST_PASSWORD: str = os.getenv("EMAIL_HOST_PASSWORD", "test_password")
    EMAIL_USE_TLS: bool = os.getenv("EMAIL_USE_TLS", "False").lower() == "true"
    MAILHOG_API_PORT: int = os.getenv("MAILHOG_API_PORT", "8025")

    PATH_TO_EMAIL_TEMPLATES_DIR: str = str(
        BASE_DIR / "src" / "online_cinema_api" / "notifications" / "templates"
    )
    ACTIVATION_EMAIL_TEMPLATE_NAME: str = "activation_request.html"
    ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME: str = "activation_complete.html"
    PASSWORD_RESET_TEMPLATE_NAME: str = "password_reset_request.html"
    PASSWORD_RESET_COMPLETE_TEMPLATE_NAME: str = "password_reset_complete.html"

    DOMAIN: str = os.getenv("DOMAIN", "localhost")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
