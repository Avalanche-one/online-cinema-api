from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from online_cinema_api.core import config as config_module
from online_cinema_api.core.config import (
    ENV_FILE,
    BaseAppSettings,
    Settings,
    get_settings,
    settings,
)
from online_cinema_api.core.exceptions import (
    AccountAlreadyActiveError,
    AccountNotActivatedError,
    AppError,
    InvalidActivationTokenError,
    InvalidCredentialsError,
    PermissionForReadUserCartError,
    RefreshTokenNotFoundError,
    UserAlreadyExistsError,
    UserGroupNotFoundError,
    UserNotFoundError,
)
from online_cinema_api.db import session as session_module


def test_env_file_points_to_dotenv():
    assert ENV_FILE.name == ".env"


def test_base_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        BaseAppSettings(_env_file=None)


def test_base_settings_defaults(monkeypatch):
    for name in ("APP_NAME", "APP_ENV", "DEBUG"):
        monkeypatch.delenv(name, raising=False)

    cfg = BaseAppSettings(_env_file=None, database_url="sqlite+aiosqlite://")

    assert cfg.app_name == "Online Cinema API"
    assert cfg.app_env == "development"
    assert cfg.debug is True
    assert cfg.database_url == "sqlite+aiosqlite://"


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    cfg = Settings(_env_file=None, database_url="sqlite+aiosqlite://")

    assert cfg.REDIS_URL == "redis://localhost:6379/0"
    assert cfg.LOGIN_TIME_DAYS == 7
    assert cfg.ACTIVATION_EMAIL_TEMPLATE_NAME == "activation_request.html"
    assert cfg.ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME == "activation_complete.html"
    assert cfg.PASSWORD_RESET_TEMPLATE_NAME == "password_reset_request.html"
    assert cfg.PASSWORD_RESET_COMPLETE_TEMPLATE_NAME == "password_reset_complete.html"
    assert cfg.PASSWORD_RESET_PAGE_TEMPLATE_NAME == "password_reset.html"
    assert cfg.PAYMENT_CONFIRMATION_TEMPLATE_NAME == "payment_confirmation.html"
    assert cfg.PATH_TO_EMAIL_TEMPLATES_DIR.replace("\\", "/").endswith(
        "online_cinema_api/notifications/templates"
    )


def test_settings_ignore_unknown_env_values(monkeypatch):
    monkeypatch.setenv("SOME_UNKNOWN_VARIABLE", "1")

    Settings(_env_file=None, database_url="sqlite+aiosqlite://")


def test_settings_read_values_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///from-env.db")
    monkeypatch.setenv("REDIS_URL", "redis://redis-host:6379/5")

    cfg = Settings(_env_file=None)

    assert cfg.database_url == "sqlite+aiosqlite:///from-env.db"
    assert cfg.REDIS_URL == "redis://redis-host:6379/5"


def test_get_settings_is_cached_and_matches_module_singleton():
    assert get_settings() is get_settings()
    assert settings is get_settings()
    assert isinstance(settings, Settings)
    assert config_module.settings is settings


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (UserAlreadyExistsError, 409, "A user with this email already exists."),
        (UserGroupNotFoundError, 500, "Default user group not found."),
        (InvalidActivationTokenError, 400, "Invalid or expired activation token."),
        (AccountAlreadyActiveError, 400, "User account is already active."),
        (InvalidCredentialsError, 401, "Invalid email or password."),
        (AccountNotActivatedError, 403, "User account is not activated."),
        (RefreshTokenNotFoundError, 401, "Refresh token not found."),
        (UserNotFoundError, 404, "User not found."),
        (PermissionForReadUserCartError, 403, "Not enough permissions"),
    ],
)
def test_account_errors_status_and_detail(error, status, detail):
    exc = error()

    assert exc.status_code == status
    assert exc.detail == detail
    assert str(exc) == detail


def test_app_error_defaults():
    exc = AppError()

    assert exc.status_code == 500
    assert exc.detail == "Internal server error"
    assert isinstance(exc, Exception)


def test_app_error_custom_detail_overrides_default():
    exc = UserNotFoundError("Custom message")

    assert exc.detail == "Custom message"
    assert str(exc) == "Custom message"
    assert exc.status_code == 404


def test_custom_detail_does_not_leak_to_class_default():
    UserNotFoundError("Custom message")

    assert UserNotFoundError.detail == "User not found."
    assert UserNotFoundError().detail == "User not found."


def test_all_app_errors_have_valid_status_and_detail():
    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    subclasses = list(walk(AppError))

    assert subclasses
    for cls in subclasses:
        assert 400 <= cls.status_code <= 599, cls
        assert isinstance(cls.detail, str) and cls.detail, cls


@pytest.fixture
def fake_session(monkeypatch):
    session = MagicMock()
    session.rollback = AsyncMock()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(session_module, "async_session_factory", lambda: _Ctx())
    return session


async def test_get_db_session_yields_session(fake_session):
    gen = session_module.get_db_session()

    assert await gen.__anext__() is fake_session
    await gen.aclose()
    fake_session.rollback.assert_not_awaited()


async def test_get_db_session_rolls_back_and_reraises_on_error(fake_session):
    gen = session_module.get_db_session()
    await gen.__anext__()

    with pytest.raises(RuntimeError, match="boom"):
        await gen.athrow(RuntimeError("boom"))

    fake_session.rollback.assert_awaited_once()


def test_engine_and_session_factory_are_configured():
    assert str(session_module.engine.url) == settings.database_url or (
        session_module.engine.url.drivername.startswith(
            settings.database_url.split(":")[0].split("+")[0]
        )
    )
    assert session_module.async_session_factory.kw["expire_on_commit"] is False
