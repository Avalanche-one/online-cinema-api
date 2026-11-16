import importlib
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from online_cinema_api.db.models.accounts import (
    ActivationTokenModel,
    GenderEnum,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserGroupEnum,
    UserProfileModel,
)

SERVICES_MODULE = "online_cinema_api.services.accounts"
svc = importlib.import_module(SERVICES_MODULE)

from .conftest import VALID_PASSWORD


async def _count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_create_user(db_session, groups):
    user = await svc.create_user(
        db_session, "new@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )

    assert user.id is not None
    assert user.email == "new@example.com"
    assert user.is_active is False
    assert user.verify_password(VALID_PASSWORD)


async def test_get_user_by_email(db_session, user_factory):
    created = await user_factory(email="find@example.com")

    assert (
        await svc.get_user_by_email(db_session, "find@example.com")
    ).id == created.id
    assert await svc.get_user_by_email(db_session, "missing@example.com") is None


async def test_get_user_by_id(db_session, user_factory):
    created = await user_factory()

    assert (await svc.get_user_by_id(db_session, created.id)).email == created.email
    assert await svc.get_user_by_id(db_session, 9999) is None


async def test_get_default_user_group(db_session, groups):
    group = await svc.get_default_user_group(db_session)

    assert group is not None
    assert group.name == UserGroupEnum.USER


async def test_get_default_user_group_returns_none_when_missing(db_session):
    assert await svc.get_default_user_group(db_session) is None


async def test_create_user_with_activation(db_session, groups):
    user, token = await svc.create_user_with_activation(
        db_session, "reg@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )

    assert user.id is not None
    assert user.is_active is False
    assert token.user_id == user.id
    assert token.token
    profile = await db_session.scalar(
        select(UserProfileModel).where(UserProfileModel.user_id == user.id)
    )
    assert profile is not None


async def test_create_user_with_activation_duplicate_email_rolls_back(
    db_session, groups
):
    group_id = groups[UserGroupEnum.USER].id
    await svc.create_user_with_activation(
        db_session, "dup@example.com", VALID_PASSWORD, group_id
    )

    with pytest.raises(IntegrityError):
        await svc.create_user_with_activation(
            db_session, "dup@example.com", VALID_PASSWORD, group_id
        )

    assert await _count(db_session, ActivationTokenModel) == 1
    assert await svc.get_user_by_email(db_session, "dup@example.com") is not None


async def test_create_user_with_activation_weak_password(db_session, groups):
    with pytest.raises(ValueError):
        await svc.create_user_with_activation(
            db_session, "weak@example.com", "weak", groups[UserGroupEnum.USER].id
        )

    assert await svc.get_user_by_email(db_session, "weak@example.com") is None


async def test_get_activation_token_with_user(db_session, groups):
    user, token = await svc.create_user_with_activation(
        db_session, "act@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )

    found = await svc.get_activation_token_with_user(
        db_session, "act@example.com", token.token
    )

    assert found is not None
    assert found.user.id == user.id


async def test_get_activation_token_with_user_no_match(db_session, groups):
    _, token = await svc.create_user_with_activation(
        db_session, "act@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )

    assert (
        await svc.get_activation_token_with_user(db_session, "act@example.com", "bad")
        is None
    )
    assert (
        await svc.get_activation_token_with_user(
            db_session, "other@example.com", token.token
        )
        is None
    )


async def test_get_activation_token_by_token(db_session, groups):
    _user, token = await svc.create_user_with_activation(
        db_session, "act@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )

    found = await svc.get_activation_token_by_token(db_session, token.token)

    assert found.user.email == "act@example.com"
    assert await svc.get_activation_token_by_token(db_session, "missing") is None


async def test_delete_token_and_commit(db_session, groups):
    _, token = await svc.create_user_with_activation(
        db_session, "act@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )

    await svc.delete_token_and_commit(db_session, token)

    assert await _count(db_session, ActivationTokenModel) == 0


async def test_activate_user_account(db_session, groups):
    user, token = await svc.create_user_with_activation(
        db_session, "act@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )
    token_value = token.token

    await svc.activate_user_account(db_session, user, token)

    assert user.is_active is True
    assert await svc.get_activation_token_by_token(db_session, token_value) is None


async def test_recreate_activation_token_replaces_old_one(db_session, user_factory):
    user = await user_factory(is_active=False)
    first = await svc.recreate_activation_token(db_session, user.id)
    first_value = first.token

    second = await svc.recreate_activation_token(db_session, user.id)

    assert second.token != first_value
    assert await _count(db_session, ActivationTokenModel) == 1
    assert await svc.get_activation_token_by_token(db_session, first_value) is None


async def test_recreate_password_reset_token_replaces_old_one(db_session, user_factory):
    user = await user_factory()
    first = await svc.recreate_password_reset_token(db_session, user.id)
    first_value = first.token

    second = await svc.recreate_password_reset_token(db_session, user.id)

    assert second.token != first_value
    assert await _count(db_session, PasswordResetTokenModel) == 1


async def test_get_password_reset_token(db_session, user_factory):
    user = await user_factory()
    assert await svc.get_password_reset_token(db_session, user.id) is None

    created = await svc.recreate_password_reset_token(db_session, user.id)

    found = await svc.get_password_reset_token(db_session, user.id)
    assert found.token == created.token


async def test_update_password_and_delete_token(db_session, user_factory):
    user = await user_factory(email="u@example.com")
    other = await user_factory(email="o@example.com")
    reset = await svc.recreate_password_reset_token(db_session, user.id)
    await svc.create_refresh_token_record(db_session, user.id, 7, "rt-user")
    await svc.create_refresh_token_record(db_session, other.id, 7, "rt-other")

    await svc.update_password_and_delete_token(db_session, user, "NewPass1!", reset)

    assert user.verify_password("NewPass1!")
    assert not user.verify_password(VALID_PASSWORD)
    assert await svc.get_password_reset_token(db_session, user.id) is None
    assert await svc.get_refresh_token_record(db_session, "rt-user") is None
    assert await svc.get_refresh_token_record(db_session, "rt-other") is not None


async def test_update_password_rejects_weak_password(db_session, user_factory):
    user = await user_factory()
    reset = await svc.recreate_password_reset_token(db_session, user.id)

    with pytest.raises(ValueError):
        await svc.update_password_and_delete_token(db_session, user, "weak", reset)

    assert user.verify_password(VALID_PASSWORD)
    assert await svc.get_password_reset_token(db_session, user.id) is not None


async def test_create_refresh_token_record(db_session, user_factory):
    user = await user_factory()
    before = datetime.now(UTC)

    record = await svc.create_refresh_token_record(db_session, user.id, 7, "my-token")

    assert record.id is not None
    assert record.token == "my-token"
    assert record.user_id == user.id
    assert (
        before + timedelta(days=7)
        <= record.expires_at
        <= datetime.now(UTC) + timedelta(days=7)
    )


async def test_create_refresh_token_record_duplicate_token(db_session, user_factory):
    user = await user_factory()
    await svc.create_refresh_token_record(db_session, user.id, 7, "same")

    with pytest.raises(IntegrityError):
        await svc.create_refresh_token_record(db_session, user.id, 7, "same")

    assert await _count(db_session, RefreshTokenModel) == 1


async def test_get_refresh_token_record(db_session, user_factory):
    user = await user_factory()
    await svc.create_refresh_token_record(db_session, user.id, 7, "tok")

    assert (await svc.get_refresh_token_record(db_session, "tok")).user_id == user.id
    assert await svc.get_refresh_token_record(db_session, "nope") is None


async def test_get_user_with_profile(db_session, groups):
    user, _ = await svc.create_user_with_activation(
        db_session, "p@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )

    loaded = await svc.get_user_with_profile(db_session, user.id)

    assert loaded.profile is not None
    assert loaded.group.name == UserGroupEnum.USER
    assert await svc.get_user_with_profile(db_session, 9999) is None


async def test_update_user_profile_creates_profile_when_missing(
    db_session, user_factory
):
    user = await user_factory()
    loaded = await svc.get_user_with_profile(db_session, user.id)
    assert loaded.profile is None

    updated = await svc.update_user_profile(
        db_session, loaded, {"first_name": "Ann", "gender": GenderEnum.WOMAN}
    )

    assert updated.profile.first_name == "Ann"
    assert updated.profile.gender is GenderEnum.WOMAN
    assert updated.profile.user_id == user.id


async def test_update_user_profile_updates_only_given_fields(db_session, groups):
    user, _ = await svc.create_user_with_activation(
        db_session, "p@example.com", VALID_PASSWORD, groups[UserGroupEnum.USER].id
    )
    loaded = await svc.get_user_with_profile(db_session, user.id)
    await svc.update_user_profile(
        db_session, loaded, {"first_name": "Ann", "last_name": "Lee"}
    )
    loaded = await svc.get_user_with_profile(db_session, user.id)

    updated = await svc.update_user_profile(
        db_session,
        loaded,
        {"first_name": "Anna", "date_of_birth": date(1990, 5, 17), "info": "hi"},
    )

    assert updated.profile.first_name == "Anna"
    assert updated.profile.last_name == "Lee"
    assert updated.profile.date_of_birth == date(1990, 5, 17)
    assert updated.profile.info == "hi"
    assert await _count(db_session, UserProfileModel) == 1
