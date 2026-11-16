from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from online_cinema_api.db.base import Base
from online_cinema_api.db.models.accounts import (
    ActivationTokenModel,
    GenderEnum,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
    UserProfileModel,
)

from .conftest import VALID_PASSWORD


def test_enum_values():
    assert {g.value for g in UserGroupEnum} == {"user", "moderator", "admin"}
    assert {g.value for g in GenderEnum} == {"man", "woman"}


def test_tables_registered_in_metadata():
    assert {
        "user_groups",
        "users",
        "user_profiles",
        "activation_tokens",
        "password_reset_tokens",
        "refresh_tokens",
    } <= set(Base.metadata.tables)


def test_password_is_write_only():
    user = UserModel(email="a@example.com", group_id=1)

    with pytest.raises(AttributeError, match="write-only"):
        _ = user.password


def test_create_hashes_password_and_sets_attributes():
    user = UserModel.create(
        email="a@example.com", raw_password=VALID_PASSWORD, group_id=3
    )

    assert user.email == "a@example.com"
    assert user.group_id == 3
    assert user._hashed_password != VALID_PASSWORD
    assert user._hashed_password.startswith("$2")


def test_verify_password():
    user = UserModel.create(
        email="a@example.com", raw_password=VALID_PASSWORD, group_id=1
    )

    assert user.verify_password(VALID_PASSWORD) is True
    assert user.verify_password("WrongPass1!") is False


def test_password_setter_rejects_weak_password():
    user = UserModel(email="a@example.com", group_id=1)

    with pytest.raises(ValueError):
        user.password = "weak"


def test_email_is_lowercased_and_normalized():
    user = UserModel(email="MiXeD@Example.COM", group_id=1)

    assert user.email == "mixed@example.com"


def test_invalid_email_is_rejected():
    with pytest.raises(ValueError):
        UserModel(email="not-an-email", group_id=1)


def test_has_group():
    user = UserModel(email="a@example.com", group_id=1)
    user.group = UserGroupModel(name=UserGroupEnum.ADMIN)

    assert user.has_group(UserGroupEnum.ADMIN) is True
    assert user.has_group(UserGroupEnum.USER) is False


def test_reprs():
    user = UserModel(email="a@example.com", group_id=1)
    assert "a@example.com" in repr(user)
    assert "UserGroupModel" in repr(UserGroupModel(name=UserGroupEnum.USER))
    assert "UserProfileModel" in repr(UserProfileModel(first_name="Ann"))
    assert "ActivationTokenModel" in repr(ActivationTokenModel())
    assert "PasswordResetTokenModel" in repr(PasswordResetTokenModel())
    assert "RefreshTokenModel" in repr(RefreshTokenModel())


def test_refresh_token_create_sets_expiration():
    before = datetime.now(UTC)
    token = RefreshTokenModel.create(user_id=1, days_valid=7, token="abc")
    after = datetime.now(UTC)

    assert token.user_id == 1
    assert token.token == "abc"
    assert before + timedelta(days=7) <= token.expires_at <= after + timedelta(days=7)


async def test_user_is_not_active_by_default(db_session, groups):
    user = UserModel.create(
        email="new@example.com",
        raw_password=VALID_PASSWORD,
        group_id=groups[UserGroupEnum.USER].id,
    )
    db_session.add(user)
    await db_session.commit()

    assert user.id is not None
    assert user.is_active is False


async def test_user_email_must_be_unique(user_factory):
    await user_factory(email="dup@example.com")

    with pytest.raises(IntegrityError):
        await user_factory(email="dup@example.com")


async def test_user_group_name_must_be_unique(db_session, groups):
    db_session.add(UserGroupModel(name=UserGroupEnum.USER))

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.parametrize(
    "model", [ActivationTokenModel, PasswordResetTokenModel, RefreshTokenModel]
)
async def test_token_defaults(db_session, user_factory, model):
    user = await user_factory()
    token = model(user_id=user.id)
    db_session.add(token)
    await db_session.commit()

    assert token.token
    assert len(token.token) == 43
    remaining = token.expires_at - datetime.now(UTC)
    assert timedelta(hours=23) < remaining <= timedelta(days=1)


@pytest.mark.parametrize("model", [ActivationTokenModel, PasswordResetTokenModel])
async def test_only_one_token_per_user(db_session, user_factory, model):
    user = await user_factory()
    db_session.add(model(user_id=user.id))
    await db_session.commit()

    db_session.add(model(user_id=user.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_user_can_have_many_refresh_tokens(db_session, user_factory):
    user = await user_factory()
    db_session.add_all(
        [
            RefreshTokenModel(user_id=user.id, token="t1"),
            RefreshTokenModel(user_id=user.id, token="t2"),
        ]
    )
    await db_session.commit()


async def test_token_value_must_be_unique(db_session, user_factory):
    user = await user_factory()
    db_session.add_all(
        [
            RefreshTokenModel(user_id=user.id, token="same"),
            RefreshTokenModel(user_id=user.id, token="same"),
        ]
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()
