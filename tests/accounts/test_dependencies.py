import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from online_cinema_api.core.exceptions import PermissionForReadUserCartError
from online_cinema_api.db.models.accounts import UserGroupEnum
from online_cinema_api.exceptions import InvalidTokenError, TokenExpiredError
from online_cinema_api.notifications import EmailSender
from online_cinema_api.schemas import UserRead
from online_cinema_api.security.token_manager import JWTAuthManager

DEPENDENCIES_MODULE = "online_cinema_api.dependencies.accounts"
deps = importlib.import_module(DEPENDENCIES_MODULE)


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        SECRET_KEY_ACCESS="dep-access",
        SECRET_KEY_REFRESH="dep-refresh",
        JWT_SIGNING_ALGORITHM="HS256",
        EMAIL_HOST="smtp.test",
        EMAIL_PORT=2525,
        EMAIL_HOST_USER="noreply@cinema.test",
        EMAIL_HOST_PASSWORD="pw",
        EMAIL_USE_TLS=True,
        PATH_TO_EMAIL_TEMPLATES_DIR="/tmp/templates",
        ACTIVATION_EMAIL_TEMPLATE_NAME="a.html",
        ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME="b.html",
        PASSWORD_RESET_TEMPLATE_NAME="c.html",
        PASSWORD_RESET_COMPLETE_TEMPLATE_NAME="d.html",
        PAYMENT_CONFIRMATION_TEMPLATE_NAME="e.html",
    )


def test_bearer_scheme_is_http_bearer():
    assert isinstance(deps.bearer_scheme, HTTPBearer)


def test_get_jwt_auth_manager_uses_settings():
    manager = deps.get_jwt_auth_manager(settings=_fake_settings())

    assert isinstance(manager, JWTAuthManager)
    reference = JWTAuthManager("dep-access", "dep-refresh", "HS256")
    token = manager.create_access_token({"sub": "a@example.com"})
    assert reference.decode_access_token(token)["sub"] == "a@example.com"
    refresh = manager.create_refresh_token({"sub": "a@example.com"})
    assert reference.decode_refresh_token(refresh)["sub"] == "a@example.com"


def test_get_accounts_email_notificator_builds_email_sender():
    sender = deps.get_accounts_email_notificator(settings=_fake_settings())

    assert isinstance(sender, EmailSender)
    assert sender._hostname == "smtp.test"
    assert sender._port == 2525
    assert sender._email == "noreply@cinema.test"
    assert sender._use_tls is True
    assert sender._payment_confirmation_email_template_name == "e.html"


async def test_get_current_user_returns_user_read(
    db_session, user_factory, jwt_manager
):
    user = await user_factory(email="me@example.com")
    token = jwt_manager.create_access_token({"sub": "me@example.com"})

    result = await deps.get_current_user(
        credentials=_credentials(token), db=db_session, jwt_manager=jwt_manager
    )

    assert isinstance(result, UserRead)
    assert result.id == user.id
    assert result.email == "me@example.com"


async def test_get_current_user_rejects_inactive_user(
    db_session, user_factory, jwt_manager
):
    await user_factory(email="me@example.com", is_active=False)
    token = jwt_manager.create_access_token({"sub": "me@example.com"})

    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(
            credentials=_credentials(token), db=db_session, jwt_manager=jwt_manager
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


async def test_get_current_user_rejects_unknown_user(db_session, groups, jwt_manager):
    token = jwt_manager.create_access_token({"sub": "ghost@example.com"})

    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(
            credentials=_credentials(token), db=db_session, jwt_manager=jwt_manager
        )

    assert exc.value.status_code == 401


async def test_get_current_user_rejects_token_without_sub(
    db_session, user_factory, jwt_manager
):
    await user_factory()
    token = jwt_manager.create_access_token({"foo": "bar"})

    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(
            credentials=_credentials(token), db=db_session, jwt_manager=jwt_manager
        )

    assert exc.value.status_code == 401


async def test_get_current_user_propagates_invalid_token(db_session, jwt_manager):
    with pytest.raises(InvalidTokenError):
        await deps.get_current_user(
            credentials=_credentials("garbage"), db=db_session, jwt_manager=jwt_manager
        )


async def test_get_current_user_propagates_expired_token(db_session, jwt_manager):
    from datetime import timedelta

    token = jwt_manager.create_access_token(
        {"sub": "a@example.com"}, expires_delta=timedelta(seconds=-1)
    )

    with pytest.raises(TokenExpiredError):
        await deps.get_current_user(
            credentials=_credentials(token), db=db_session, jwt_manager=jwt_manager
        )


async def test_get_current_user_rejects_refresh_token(
    db_session, user_factory, jwt_manager
):
    await user_factory(email="me@example.com")
    token = jwt_manager.create_refresh_token({"sub": "me@example.com"})

    with pytest.raises(InvalidTokenError):
        await deps.get_current_user(
            credentials=_credentials(token), db=db_session, jwt_manager=jwt_manager
        )


@pytest.mark.parametrize(
    ("group", "allowed"),
    [
        (UserGroupEnum.USER, False),
        (UserGroupEnum.MODERATOR, True),
        (UserGroupEnum.ADMIN, True),
    ],
)
async def test_required_moderator_or_admin(db_session, user_factory, group, allowed):
    user = await user_factory(group=group)
    current = UserRead(id=user.id, email=user.email)

    if allowed:
        result = await deps.required_moderator_or_admin(
            current_user=current, db=db_session
        )
        assert result is current
    else:
        with pytest.raises(PermissionForReadUserCartError):
            await deps.required_moderator_or_admin(current_user=current, db=db_session)


@pytest.mark.parametrize(
    ("group", "allowed"),
    [
        (UserGroupEnum.USER, False),
        (UserGroupEnum.MODERATOR, False),
        (UserGroupEnum.ADMIN, True),
    ],
)
async def test_required_admin(db_session, user_factory, group, allowed):
    user = await user_factory(group=group)
    current = UserRead(id=user.id, email=user.email)

    if allowed:
        assert await deps.required_admin(current_user=current, db=db_session) is current
    else:
        with pytest.raises(PermissionForReadUserCartError):
            await deps.required_admin(current_user=current, db=db_session)


async def test_role_checks_reject_user_missing_in_db(db_session, groups):
    ghost = UserRead(id=9999, email="ghost@example.com")

    with pytest.raises(PermissionForReadUserCartError):
        await deps.required_moderator_or_admin(current_user=ghost, db=db_session)
    with pytest.raises(PermissionForReadUserCartError):
        await deps.required_admin(current_user=ghost, db=db_session)
