from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from online_cinema_api import main
from online_cinema_api.core.config import settings
from online_cinema_api.core.exceptions import (
    AppError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from online_cinema_api.exceptions import (
    BaseEmailError,
    BaseSecurityError,
    InvalidTokenError,
    TokenExpiredError,
)


def test_app_metadata():
    assert main.app.title == settings.app_name
    assert main.app.version == "0.1.0"
    assert main.app.debug is settings.debug


def test_exception_handlers_are_registered():
    assert main.app.exception_handlers[AppError] is main.app_error_handler
    assert main.app.exception_handlers[BaseSecurityError] is main.security_error_handler
    assert main.app.exception_handlers[BaseEmailError] is main.email_error_handler


def test_api_routes_use_v1_prefix():
    paths = list(main.app.openapi()["paths"])

    assert paths
    assert all(path.startswith("/api/v1") for path in paths)


async def test_lifespan_disposes_engine_on_shutdown(monkeypatch):
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    monkeypatch.setattr(main, "engine", fake_engine)

    async with main.lifespan(main.app):
        fake_engine.dispose.assert_not_awaited()

    fake_engine.dispose.assert_awaited_once()


async def test_lifespan_disposes_engine_even_on_error(monkeypatch):
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    monkeypatch.setattr(main, "engine", fake_engine)

    with pytest.raises(RuntimeError):
        async with main.lifespan(main.app):
            raise RuntimeError("boom")

    fake_engine.dispose.assert_awaited_once()


@pytest_asyncio.fixture
async def client():
    """A separate app with the same exception handlers as main.app."""
    app = FastAPI()
    app.add_exception_handler(AppError, main.app_error_handler)
    app.add_exception_handler(BaseSecurityError, main.security_error_handler)
    app.add_exception_handler(BaseEmailError, main.email_error_handler)

    @app.get("/user-not-found")
    async def user_not_found():
        raise UserNotFoundError

    @app.get("/bad-credentials")
    async def bad_credentials():
        raise InvalidCredentialsError

    @app.get("/custom-detail")
    async def custom_detail():
        raise UserNotFoundError("Nobody here")

    @app.get("/base-app-error")
    async def base_app_error():
        raise AppError

    @app.get("/token-expired")
    async def token_expired():
        raise TokenExpiredError

    @app.get("/invalid-token")
    async def invalid_token():
        raise InvalidTokenError

    @app.get("/email-error")
    async def email_error():
        raise BaseEmailError("smtp password is hunter2")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.mark.parametrize(
    ("path", "status", "detail"),
    [
        ("/user-not-found", 404, "User not found."),
        ("/bad-credentials", 401, "Invalid email or password."),
        ("/custom-detail", 404, "Nobody here"),
        ("/base-app-error", 500, "Internal server error"),
    ],
)
async def test_app_error_handler(client, path, status, detail):
    response = await client.get(path)

    assert response.status_code == status
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    ("path", "detail"),
    [
        ("/token-expired", "Token has expired."),
        ("/invalid-token", "Invalid token."),
    ],
)
async def test_security_error_handler(client, path, detail):
    response = await client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": detail}
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_email_error_handler_hides_internal_message(client):
    response = await client.get("/email-error")

    assert response.status_code == 503
    assert response.json() == {"detail": "Email service is temporarily unavailable."}
    assert "hunter2" not in response.text
