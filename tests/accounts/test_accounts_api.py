"""Tests for the endpoints in online_cinema_api/api/accounts.py.

The router is mounted on a separate FastAPI app with the same error handlers
as main.py. The database (in-memory SQLite), the JWT manager and the email
sender are replaced through dependency_overrides.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jinja2 import DictLoader, Environment, select_autoescape
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from online_cinema_api import main
from online_cinema_api.api import accounts as accounts_api
from online_cinema_api.core.config import settings
from online_cinema_api.core.exceptions import AppError
from online_cinema_api.db.models.accounts import (
    ActivationTokenModel,
    PasswordResetTokenModel,
    UserGroupEnum,
    UserModel,
)
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies import (
    get_accounts_email_notificator,
    get_jwt_auth_manager,
)
from online_cinema_api.exceptions import BaseEmailError, BaseSecurityError
from online_cinema_api.notifications.interfaces import EmailSenderInterface
from online_cinema_api.services import accounts as svc

from .conftest import VALID_PASSWORD

BASE = "/api/v1/accounts"
NEW_PASSWORD = "NewPass1!"


class FakeEmailSender(EmailSenderInterface):
    """Records which emails were "sent"."""

    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_activation_email(self, email, activation_link):
        self.sent.append(("activation", email, activation_link))

    async def send_activation_complete_email(self, email, login_link):
        self.sent.append(("activation_complete", email, login_link))

    async def send_password_reset_email(self, email, reset_link):
        self.sent.append(("password_reset", email, reset_link))

    async def send_password_reset_complete_email(self, email, login_link):
        self.sent.append(("password_reset_complete", email, login_link))

    async def send_payment_confirmation_email(self, email, order_id, amount, movies):
        self.sent.append(("payment", email, order_id, amount, movies))


@pytest.fixture
def email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def app(db_session, jwt_manager, email_sender) -> FastAPI:
    application = FastAPI()
    application.add_exception_handler(AppError, main.app_error_handler)
    application.add_exception_handler(BaseSecurityError, main.security_error_handler)
    application.add_exception_handler(BaseEmailError, main.email_error_handler)
    application.include_router(accounts_api.router, prefix=BASE)

    async def _db():
        return db_session

    application.dependency_overrides[get_db_session] = _db
    application.dependency_overrides[get_jwt_auth_manager] = lambda: jwt_manager
    application.dependency_overrides[get_accounts_email_notificator] = lambda: (
        email_sender
    )
    return application


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture
def auth(jwt_manager):
    def _headers(user: UserModel) -> dict[str, str]:
        token = jwt_manager.create_access_token({"sub": user.email, "user_id": user.id})
        return {"Authorization": f"Bearer {token}"}

    return _headers


async def _only_token(db, model) -> str:
    return await db.scalar(select(model.token))


async def _expire_first(db, model) -> None:
    record = await db.scalar(select(model))
    record.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()


def _credentials(email="user@example.com", password=VALID_PASSWORD) -> dict:
    return {"email": email, "password": password}


async def test_register_creates_inactive_user_and_sends_activation_email(
    client, db_session, groups, email_sender
):
    response = await client.post(f"{BASE}/register/", json=_credentials())

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert "id" in body
    assert "password" not in body

    user = await svc.get_user_by_email(db_session, "user@example.com")
    assert user is not None and user.is_active is False
    token = await _only_token(db_session, ActivationTokenModel)
    assert email_sender.sent == [
        (
            "activation",
            "user@example.com",
            f"{settings.DOMAIN}/api/v1/accounts/activate/?token={token}",
        )
    ]


async def test_register_lowercases_email(client, groups):
    response = await client.post(
        f"{BASE}/register/", json=_credentials(email="User@Example.COM")
    )

    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"


async def test_register_duplicate_email(client, groups, user_factory, email_sender):
    await user_factory(email="user@example.com")

    response = await client.post(f"{BASE}/register/", json=_credentials())

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    assert email_sender.sent == []


async def test_register_fails_without_default_group(client, email_sender):
    response = await client.post(f"{BASE}/register/", json=_credentials())

    assert response.status_code == 500
    assert response.json() == {"detail": "Default user group not found."}
    assert email_sender.sent == []


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": VALID_PASSWORD},
        {"email": "user@example.com", "password": "weak"},
        {"email": "user@example.com"},
        {},
    ],
)
async def test_register_validation_errors(client, groups, payload):
    response = await client.post(f"{BASE}/register/", json=payload)

    assert response.status_code == 422


async def test_register_database_error(client, groups, monkeypatch, email_sender):
    monkeypatch.setattr(
        accounts_api.accounts_crud,
        "create_user_with_activation",
        AsyncMock(side_effect=SQLAlchemyError("boom")),
    )

    response = await client.post(f"{BASE}/register/", json=_credentials())

    assert response.status_code == 500
    assert response.json() == {"detail": "An error occurred during user creation."}
    assert email_sender.sent == []


async def test_activate_account(client, db_session, groups, email_sender):
    await client.post(f"{BASE}/register/", json=_credentials())
    token = await _only_token(db_session, ActivationTokenModel)
    email_sender.sent.clear()

    response = await client.get(f"{BASE}/activate/", params={"token": token})

    assert response.status_code == 200
    assert response.json() == {"message": "User account activated successfully."}
    user = await svc.get_user_by_email(db_session, "user@example.com")
    assert user.is_active is True
    assert await svc.get_activation_token_by_token(db_session, token) is None
    assert email_sender.sent == [
        (
            "activation_complete",
            "user@example.com",
            f"{settings.DOMAIN}/api/v1/accounts/login/",
        )
    ]


async def test_activate_account_unknown_token(client, groups):
    response = await client.get(f"{BASE}/activate/", params={"token": "nope"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired activation token."}


async def test_activate_account_requires_token_param(client):
    response = await client.get(f"{BASE}/activate/")

    assert response.status_code == 422


async def test_activate_account_expired_token_is_deleted(client, db_session, groups):
    await client.post(f"{BASE}/register/", json=_credentials())
    token = await _only_token(db_session, ActivationTokenModel)
    await _expire_first(db_session, ActivationTokenModel)

    response = await client.get(f"{BASE}/activate/", params={"token": token})

    assert response.status_code == 400
    assert await svc.get_activation_token_by_token(db_session, token) is None
    user = await svc.get_user_by_email(db_session, "user@example.com")
    assert user.is_active is False


async def test_activate_account_already_active(client, db_session, user_factory):
    user = await user_factory(is_active=True)
    token_record = ActivationTokenModel(user_id=user.id)
    db_session.add(token_record)
    await db_session.commit()

    response = await client.get(
        f"{BASE}/activate/", params={"token": token_record.token}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "User account is already active."}


GENERIC_RESET_MESSAGE = (
    "If you are registered, you will receive an email with instructions."
)


async def test_password_reset_request_for_active_user(
    client, db_session, user_factory, email_sender
):
    await user_factory(email="user@example.com", is_active=True)

    response = await client.post(
        f"{BASE}/password-reset/request/", json={"email": "user@example.com"}
    )

    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_RESET_MESSAGE}
    token = await _only_token(db_session, PasswordResetTokenModel)
    kind, recipient, link = email_sender.sent[0]
    assert (kind, recipient) == ("password_reset", "user@example.com")
    assert f"email=user%40example.com&token={token}" in link
    assert "/api/v1/accounts/password-reset/complete/" in link


async def test_password_reset_request_replaces_previous_token(
    client, db_session, user_factory
):
    await user_factory(is_active=True)
    payload = {"email": "user@example.com"}

    await client.post(f"{BASE}/password-reset/request/", json=payload)
    first = await _only_token(db_session, PasswordResetTokenModel)
    await client.post(f"{BASE}/password-reset/request/", json=payload)

    tokens = (await db_session.scalars(select(PasswordResetTokenModel))).all()
    assert len(tokens) == 1
    assert tokens[0].token != first


@pytest.mark.parametrize("registered", ["unknown", "inactive"])
async def test_password_reset_request_does_not_reveal_account(
    client, db_session, user_factory, email_sender, registered
):
    if registered == "inactive":
        await user_factory(email="user@example.com", is_active=False)

    response = await client.post(
        f"{BASE}/password-reset/request/", json={"email": "user@example.com"}
    )

    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_RESET_MESSAGE}
    assert email_sender.sent == []
    assert (await db_session.scalars(select(PasswordResetTokenModel))).all() == []


async def test_password_reset_request_invalid_email(client):
    response = await client.post(
        f"{BASE}/password-reset/request/", json={"email": "nope"}
    )

    assert response.status_code == 422


async def test_password_reset_page_renders_html(client, monkeypatch):
    env = Environment(
        loader=DictLoader(
            {settings.PASSWORD_RESET_PAGE_TEMPLATE_NAME: "PAGE {{ email }} {{ token }}"}
        ),
        autoescape=select_autoescape(["html"]),
    )
    monkeypatch.setattr(accounts_api, "jinja_env", env)

    response = await client.get(
        f"{BASE}/password-reset/complete/",
        params={"email": "user@example.com", "token": "<b>tok</b>"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "PAGE user@example.com" in response.text
    assert "<b>" not in response.text
    assert "&lt;b&gt;tok" in response.text


async def test_password_reset_page_requires_params(client):
    response = await client.get(f"{BASE}/password-reset/complete/")

    assert response.status_code == 422


async def _prepare_reset(db_session, user_factory, **user_kwargs):
    user = await user_factory(**user_kwargs)
    record = await svc.recreate_password_reset_token(db_session, user.id)
    return user, record.token


def _reset_payload(token, email="user@example.com", password=NEW_PASSWORD):
    return {"email": email, "password": password, "token": token}


async def test_reset_password_success(client, db_session, user_factory, email_sender):
    user, token = await _prepare_reset(db_session, user_factory, is_active=True)
    await svc.create_refresh_token_record(db_session, user.id, 7, "old-refresh")

    response = await client.post(
        f"{BASE}/password-reset/complete/", json=_reset_payload(token)
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Password reset successfully."}
    assert await svc.get_password_reset_token(db_session, user.id) is None
    assert await svc.get_refresh_token_record(db_session, "old-refresh") is None
    assert email_sender.sent == [
        (
            "password_reset_complete",
            "user@example.com",
            f"{settings.DOMAIN}/api/v1/accounts/login/",
        )
    ]
    ok = await client.post(f"{BASE}/login/", json=_credentials(password=NEW_PASSWORD))
    old = await client.post(f"{BASE}/login/", json=_credentials())
    assert ok.status_code == 201
    assert old.status_code == 401


async def test_reset_password_unknown_user(client, db_session, groups):
    response = await client.post(
        f"{BASE}/password-reset/complete/", json=_reset_payload("tok")
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid email or token."}


async def test_reset_password_inactive_user(client, db_session, user_factory):
    _, token = await _prepare_reset(db_session, user_factory, is_active=False)

    response = await client.post(
        f"{BASE}/password-reset/complete/", json=_reset_payload(token)
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid email or token."}


async def test_reset_password_wrong_token(client, db_session, user_factory):
    user, _ = await _prepare_reset(db_session, user_factory, is_active=True)

    response = await client.post(
        f"{BASE}/password-reset/complete/", json=_reset_payload("wrong")
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid email or token."}
    assert await svc.get_password_reset_token(db_session, user.id) is not None


async def test_reset_password_without_issued_token(client, user_factory):
    await user_factory(is_active=True)

    response = await client.post(
        f"{BASE}/password-reset/complete/", json=_reset_payload("tok")
    )

    assert response.status_code == 400


async def test_reset_password_expired_token_is_deleted(
    client, db_session, user_factory
):
    user, token = await _prepare_reset(db_session, user_factory, is_active=True)
    await _expire_first(db_session, PasswordResetTokenModel)

    response = await client.post(
        f"{BASE}/password-reset/complete/", json=_reset_payload(token)
    )

    assert response.status_code == 400
    assert await svc.get_password_reset_token(db_session, user.id) is None


async def test_reset_password_rejects_weak_password(client, db_session, user_factory):
    _, token = await _prepare_reset(db_session, user_factory, is_active=True)

    response = await client.post(
        f"{BASE}/password-reset/complete/", json=_reset_payload(token, password="weak")
    )

    assert response.status_code == 422


async def test_reset_password_database_error(
    client, db_session, user_factory, monkeypatch, email_sender
):
    _, token = await _prepare_reset(db_session, user_factory, is_active=True)
    monkeypatch.setattr(
        accounts_api.accounts_crud,
        "update_password_and_delete_token",
        AsyncMock(side_effect=SQLAlchemyError("boom")),
    )

    response = await client.post(
        f"{BASE}/password-reset/complete/", json=_reset_payload(token)
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "An error occurred while resetting the password."
    }
    assert email_sender.sent == []


async def test_login_success(client, db_session, user_factory, jwt_manager):
    user = await user_factory(is_active=True)

    response = await client.post(f"{BASE}/login/", json=_credentials())

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    access = jwt_manager.decode_access_token(body["access_token"])
    refresh = jwt_manager.decode_refresh_token(body["refresh_token"])
    assert access["sub"] == "user@example.com"
    assert access["user_id"] == user.id
    assert refresh["user_id"] == user.id
    record = await svc.get_refresh_token_record(db_session, body["refresh_token"])
    assert record is not None and record.user_id == user.id


async def test_login_email_is_case_insensitive(client, user_factory):
    await user_factory(is_active=True)

    response = await client.post(
        f"{BASE}/login/", json=_credentials(email="USER@Example.com")
    )

    assert response.status_code == 201


async def test_login_multiple_sessions_get_distinct_refresh_tokens(
    client, user_factory
):
    await user_factory(is_active=True)

    first = (await client.post(f"{BASE}/login/", json=_credentials())).json()
    second = (await client.post(f"{BASE}/login/", json=_credentials())).json()

    assert first["refresh_token"] != second["refresh_token"]


@pytest.mark.parametrize(
    "payload",
    [
        _credentials(password="WrongPass1!"),
        _credentials(email="ghost@example.com"),
    ],
)
async def test_login_invalid_credentials(client, user_factory, payload):
    await user_factory(is_active=True)

    response = await client.post(f"{BASE}/login/", json=payload)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


async def test_login_inactive_account(client, user_factory):
    await user_factory(is_active=False)

    response = await client.post(f"{BASE}/login/", json=_credentials())

    assert response.status_code == 403
    assert response.json() == {"detail": "User account is not activated."}


async def test_login_inactive_account_with_wrong_password_gives_401(
    client, user_factory
):
    await user_factory(is_active=False)

    response = await client.post(
        f"{BASE}/login/", json=_credentials(password="WrongPass1!")
    )

    assert response.status_code == 401


async def test_login_does_not_enforce_password_strength(client, user_factory):
    await user_factory(is_active=True)

    response = await client.post(f"{BASE}/login/", json=_credentials(password="weak"))

    assert response.status_code == 401


async def test_login_invalid_email_format(client):
    response = await client.post(f"{BASE}/login/", json=_credentials(email="nope"))

    assert response.status_code == 422


async def test_login_database_error(client, user_factory, monkeypatch):
    await user_factory(is_active=True)
    monkeypatch.setattr(
        accounts_api.accounts_crud,
        "create_refresh_token_record",
        AsyncMock(side_effect=SQLAlchemyError("boom")),
    )

    response = await client.post(f"{BASE}/login/", json=_credentials())

    assert response.status_code == 500
    assert response.json() == {
        "detail": "An error occurred while processing the request."
    }


async def _login(client) -> dict:
    return (await client.post(f"{BASE}/login/", json=_credentials())).json()


async def test_refresh_returns_new_access_token(client, user_factory, jwt_manager):
    user = await user_factory(is_active=True)
    tokens = await _login(client)

    response = await client.post(
        f"{BASE}/refresh/", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = jwt_manager.decode_access_token(body["access_token"])
    assert payload["sub"] == "user@example.com"
    assert payload["user_id"] == user.id


async def test_refresh_with_garbage_token(client):
    response = await client.post(f"{BASE}/refresh/", json={"refresh_token": "garbage"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token."}
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_refresh_with_expired_token(client, user_factory, jwt_manager):
    user = await user_factory(is_active=True)
    expired = jwt_manager.create_refresh_token(
        {"user_id": user.id}, expires_delta=timedelta(seconds=-1)
    )

    response = await client.post(f"{BASE}/refresh/", json={"refresh_token": expired})

    assert response.status_code == 401
    assert response.json() == {"detail": "Token has expired."}


async def test_refresh_rejects_access_token(client, user_factory):
    await user_factory(is_active=True)
    tokens = await _login(client)

    response = await client.post(
        f"{BASE}/refresh/", json={"refresh_token": tokens["access_token"]}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token."}


async def test_refresh_with_valid_jwt_missing_in_database(
    client, user_factory, jwt_manager
):
    user = await user_factory(is_active=True)
    unsaved = jwt_manager.create_refresh_token({"user_id": user.id})

    response = await client.post(f"{BASE}/refresh/", json={"refresh_token": unsaved})

    assert response.status_code == 401
    assert response.json() == {"detail": "Refresh token not found."}


async def test_refresh_for_deactivated_user(client, db_session, user_factory):
    user = await user_factory(is_active=True)
    tokens = await _login(client)
    user.is_active = False
    await db_session.commit()

    response = await client.post(
        f"{BASE}/refresh/", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found."}


RESEND_MESSAGE = "If the account exists and is inactive, a new token has been sent."


async def test_resend_activation_for_inactive_user(
    client, db_session, groups, email_sender
):
    await client.post(f"{BASE}/register/", json=_credentials())
    old_token = await _only_token(db_session, ActivationTokenModel)
    email_sender.sent.clear()

    response = await client.post(
        f"{BASE}/resend-activation/", json={"email": "user@example.com"}
    )

    assert response.status_code == 200
    assert response.json() == {"message": RESEND_MESSAGE}
    new_token = await _only_token(db_session, ActivationTokenModel)
    assert new_token != old_token
    assert email_sender.sent == [
        (
            "activation",
            "user@example.com",
            f"{settings.DOMAIN}/api/v1/accounts/activate/?token={new_token}",
        )
    ]


@pytest.mark.parametrize("registered", ["unknown", "active"])
async def test_resend_activation_does_not_reveal_account(
    client, user_factory, email_sender, registered
):
    if registered == "active":
        await user_factory(email="user@example.com", is_active=True)

    response = await client.post(
        f"{BASE}/resend-activation/", json={"email": "user@example.com"}
    )

    assert response.status_code == 200
    assert response.json() == {"message": RESEND_MESSAGE}
    assert email_sender.sent == []


async def test_resend_activation_invalid_email(client):
    response = await client.post(f"{BASE}/resend-activation/", json={"email": "nope"})

    assert response.status_code == 422


async def test_logout_removes_refresh_token(client, db_session, user_factory):
    await user_factory(is_active=True)
    tokens = await _login(client)

    response = await client.post(
        f"{BASE}/logout/", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Successfully logged out."}
    assert (
        await svc.get_refresh_token_record(db_session, tokens["refresh_token"]) is None
    )
    refresh = await client.post(
        f"{BASE}/refresh/", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh.status_code == 401


async def test_logout_with_unknown_token_is_idempotent(client):
    response = await client.post(f"{BASE}/logout/", json={"refresh_token": "unknown"})

    assert response.status_code == 200
    assert response.json() == {"message": "Successfully logged out."}


async def test_logout_keeps_other_sessions(client, db_session, user_factory):
    await user_factory(is_active=True)
    first = await _login(client)
    second = await _login(client)

    await client.post(f"{BASE}/logout/", json={"refresh_token": first["refresh_token"]})

    assert await svc.get_refresh_token_record(db_session, second["refresh_token"])


async def test_admin_activate_requires_authentication(client, user_factory):
    target = await user_factory(email="t@example.com", is_active=False)

    response = await client.patch(f"{BASE}/admin/users/{target.id}/activate/")

    assert response.status_code in (401, 403)


async def test_admin_activate_rejects_regular_user(client, user_factory, auth):
    actor = await user_factory(email="a@example.com")
    target = await user_factory(email="t@example.com", is_active=False)

    response = await client.patch(
        f"{BASE}/admin/users/{target.id}/activate/", headers=auth(actor)
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}


@pytest.mark.parametrize("group", [UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN])
async def test_admin_activate_allowed_for_moderator_and_admin(
    client, db_session, user_factory, auth, group
):
    actor = await user_factory(email="a@example.com", group=group)
    target = await user_factory(email="t@example.com", is_active=False)

    response = await client.patch(
        f"{BASE}/admin/users/{target.id}/activate/", headers=auth(actor)
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "User t@example.com has been manually activated."
    }
    await db_session.refresh(target)
    assert target.is_active is True


async def test_admin_activate_unknown_user(client, user_factory, auth):
    actor = await user_factory(email="a@example.com", group=UserGroupEnum.ADMIN)

    response = await client.patch(
        f"{BASE}/admin/users/9999/activate/", headers=auth(actor)
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found."}


async def test_admin_change_group_success(
    client, db_session, groups, user_factory, auth
):
    actor = await user_factory(email="a@example.com", group=UserGroupEnum.ADMIN)
    target = await user_factory(email="t@example.com")
    moderator_id = groups[UserGroupEnum.MODERATOR].id

    response = await client.patch(
        f"{BASE}/admin/users/{target.id}/group/",
        params={"new_group_id": moderator_id},
        headers=auth(actor),
    )

    assert response.status_code == 200
    assert response.json() == {"message": "User group updated successfully."}
    await db_session.refresh(target)
    assert target.group_id == moderator_id


@pytest.mark.parametrize("group", [UserGroupEnum.USER, UserGroupEnum.MODERATOR])
async def test_admin_change_group_forbidden_for_non_admin(
    client, groups, user_factory, auth, group
):
    actor = await user_factory(email="a@example.com", group=group)
    target = await user_factory(email="t@example.com")

    response = await client.patch(
        f"{BASE}/admin/users/{target.id}/group/",
        params={"new_group_id": groups[UserGroupEnum.ADMIN].id},
        headers=auth(actor),
    )

    assert response.status_code == 403


async def test_admin_change_group_unknown_user(client, groups, user_factory, auth):
    actor = await user_factory(email="a@example.com", group=UserGroupEnum.ADMIN)

    response = await client.patch(
        f"{BASE}/admin/users/9999/group/",
        params={"new_group_id": groups[UserGroupEnum.USER].id},
        headers=auth(actor),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found."}


async def test_admin_change_group_unknown_group(client, user_factory, auth):
    actor = await user_factory(email="a@example.com", group=UserGroupEnum.ADMIN)
    target = await user_factory(email="t@example.com")

    response = await client.patch(
        f"{BASE}/admin/users/{target.id}/group/",
        params={"new_group_id": 9999},
        headers=auth(actor),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Group not found."}


async def test_admin_change_group_requires_new_group_id(client, user_factory, auth):
    actor = await user_factory(email="a@example.com", group=UserGroupEnum.ADMIN)

    response = await client.patch(f"{BASE}/admin/users/1/group/", headers=auth(actor))

    assert response.status_code == 422


async def test_get_me(client, user_factory, auth):
    user = await user_factory(is_active=True)

    response = await client.get(f"{BASE}/me/", headers=auth(user))

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "email": "user@example.com",
        "is_active": True,
        "group": "user",
        "profile": None,
    }


async def test_get_me_reports_group(client, user_factory, auth):
    user = await user_factory(group=UserGroupEnum.ADMIN)

    response = await client.get(f"{BASE}/me/", headers=auth(user))

    assert response.json()["group"] == "admin"


async def test_get_me_requires_authentication(client):
    response = await client.get(f"{BASE}/me/")

    assert response.status_code in (401, 403)


async def test_get_me_with_invalid_token(client):
    response = await client.get(
        f"{BASE}/me/", headers={"Authorization": "Bearer garbage"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token."}


async def test_get_me_rejects_inactive_user(client, user_factory, auth):
    user = await user_factory(is_active=False)

    response = await client.get(f"{BASE}/me/", headers=auth(user))

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}


async def test_get_me_rejects_refresh_token(client, user_factory, jwt_manager):
    user = await user_factory()
    refresh = jwt_manager.create_refresh_token({"sub": user.email})

    response = await client.get(
        f"{BASE}/me/", headers={"Authorization": f"Bearer {refresh}"}
    )

    assert response.status_code == 401


async def test_update_me_creates_profile(client, user_factory, auth):
    user = await user_factory()

    response = await client.patch(
        f"{BASE}/me/",
        headers=auth(user),
        json={
            "first_name": "  Ann ",
            "last_name": "Lee",
            "gender": "woman",
            "date_of_birth": "1990-05-17",
            "info": "Hello",
        },
    )

    assert response.status_code == 200
    assert response.json()["profile"] == {
        "first_name": "Ann",
        "last_name": "Lee",
        "avatar": None,
        "gender": "woman",
        "date_of_birth": "1990-05-17",
        "info": "Hello",
    }


async def test_update_me_is_partial(client, user_factory, auth):
    user = await user_factory()
    await client.patch(
        f"{BASE}/me/",
        headers=auth(user),
        json={"first_name": "Ann", "last_name": "Lee"},
    )

    response = await client.patch(
        f"{BASE}/me/", headers=auth(user), json={"info": "Hi"}
    )

    profile = response.json()["profile"]
    assert profile["first_name"] == "Ann"
    assert profile["last_name"] == "Lee"
    assert profile["info"] == "Hi"


async def test_update_me_explicit_null_clears_field(client, user_factory, auth):
    user = await user_factory()
    await client.patch(f"{BASE}/me/", headers=auth(user), json={"first_name": "Ann"})

    response = await client.patch(
        f"{BASE}/me/", headers=auth(user), json={"first_name": None}
    )

    assert response.json()["profile"]["first_name"] is None


async def test_update_me_blank_name_becomes_null(client, user_factory, auth):
    user = await user_factory()

    response = await client.patch(
        f"{BASE}/me/", headers=auth(user), json={"first_name": "   "}
    )

    assert response.status_code == 200
    assert response.json()["profile"]["first_name"] is None


async def test_update_me_is_visible_in_get_me(client, user_factory, auth):
    user = await user_factory()
    await client.patch(f"{BASE}/me/", headers=auth(user), json={"first_name": "Ann"})

    response = await client.get(f"{BASE}/me/", headers=auth(user))

    assert response.json()["profile"]["first_name"] == "Ann"


@pytest.mark.parametrize(
    "payload",
    [
        {"avatar": "http://x/y.png"},
        {"gender": "other"},
        {"first_name": "a" * 101},
        {"date_of_birth": (datetime.now(UTC) + timedelta(days=2)).date().isoformat()},
        {"date_of_birth": "not-a-date"},
    ],
)
async def test_update_me_validation_errors(client, user_factory, auth, payload):
    user = await user_factory()

    response = await client.patch(f"{BASE}/me/", headers=auth(user), json=payload)

    assert response.status_code == 422


async def test_update_me_requires_authentication(client):
    response = await client.patch(f"{BASE}/me/", json={"first_name": "Ann"})

    assert response.status_code in (401, 403)


async def test_update_me_database_error(client, user_factory, auth, monkeypatch):
    user = await user_factory()
    monkeypatch.setattr(
        accounts_api.accounts_crud,
        "update_user_profile",
        AsyncMock(side_effect=SQLAlchemyError("boom")),
    )

    response = await client.patch(
        f"{BASE}/me/", headers=auth(user), json={"first_name": "Ann"}
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "An error occurred while updating the profile."
    }
