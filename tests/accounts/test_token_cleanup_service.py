"""Tests for online_cinema_api/services/token_cleanup.py.

The `expires_at <= now()` comparison runs on SQLite (CURRENT_TIMESTAMP, UTC),
so all times in the tests are offset from the current moment by hours, not
seconds.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select

from online_cinema_api.db.models.accounts import (
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserModel,
)
from online_cinema_api.services import token_cleanup
from online_cinema_api.services.token_cleanup import (
    EXPIRING_MODELS,
    delete_expired_tokens,
)

PAST = timedelta(hours=-2)
FUTURE = timedelta(hours=2)


async def _count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def _add(db, model, user_id: int, delta: timedelta) -> None:
    db.add(model(user_id=user_id, expires_at=datetime.now(UTC) + delta))
    await db.commit()


def test_expiring_models_cover_all_token_tables():
    assert set(EXPIRING_MODELS) == {
        ActivationTokenModel,
        PasswordResetTokenModel,
        RefreshTokenModel,
    }


async def test_returns_zero_counts_for_every_table_when_empty(db_session, groups):
    result = await delete_expired_tokens(db_session)

    assert result == {
        "activation_tokens": 0,
        "password_reset_tokens": 0,
        "refresh_tokens": 0,
    }


@pytest.mark.parametrize(
    "model", [ActivationTokenModel, PasswordResetTokenModel, RefreshTokenModel]
)
async def test_deletes_only_expired_tokens(db_session, user_factory, model):
    expired_owner = await user_factory(email="expired@example.com")
    valid_owner = await user_factory(email="valid@example.com")
    await _add(db_session, model, expired_owner.id, PAST)
    await _add(db_session, model, valid_owner.id, FUTURE)

    result = await delete_expired_tokens(db_session)

    assert result[model.__tablename__] == 1
    remaining = (await db_session.scalars(select(model))).all()
    assert [t.user_id for t in remaining] == [valid_owner.id]


async def test_counts_are_reported_per_table(db_session, user_factory):
    first = await user_factory(email="a@example.com")
    second = await user_factory(email="b@example.com")
    await _add(db_session, ActivationTokenModel, first.id, PAST)
    await _add(db_session, ActivationTokenModel, second.id, PAST)
    await _add(db_session, PasswordResetTokenModel, first.id, PAST)
    await _add(db_session, RefreshTokenModel, first.id, PAST)
    await _add(db_session, RefreshTokenModel, first.id, PAST)
    await _add(db_session, RefreshTokenModel, first.id, PAST)
    await _add(db_session, RefreshTokenModel, first.id, FUTURE)

    result = await delete_expired_tokens(db_session)

    assert result == {
        "activation_tokens": 2,
        "password_reset_tokens": 1,
        "refresh_tokens": 3,
    }
    assert await _count(db_session, RefreshTokenModel) == 1


async def test_keeps_all_valid_tokens(db_session, user_factory):
    user = await user_factory()
    await _add(db_session, ActivationTokenModel, user.id, FUTURE)
    await _add(db_session, PasswordResetTokenModel, user.id, FUTURE)
    await _add(db_session, RefreshTokenModel, user.id, FUTURE)

    result = await delete_expired_tokens(db_session)

    assert set(result.values()) == {0}
    for model in EXPIRING_MODELS:
        assert await _count(db_session, model) == 1


async def test_does_not_delete_users(db_session, user_factory):
    user = await user_factory()
    await _add(db_session, RefreshTokenModel, user.id, PAST)

    await delete_expired_tokens(db_session)

    assert await _count(db_session, UserModel) == 1


async def test_second_run_is_idempotent(db_session, user_factory):
    user = await user_factory()
    await _add(db_session, RefreshTokenModel, user.id, PAST)

    first = await delete_expired_tokens(db_session)
    second = await delete_expired_tokens(db_session)

    assert first["refresh_tokens"] == 1
    assert second["refresh_tokens"] == 0


def _fake_db(execute=None, commit=None) -> MagicMock:
    db = MagicMock()
    db.execute = execute or AsyncMock(return_value=MagicMock(rowcount=0))
    db.commit = commit or AsyncMock()
    db.rollback = AsyncMock()
    return db


async def test_rolls_back_and_reraises_when_delete_fails():
    db = _fake_db(execute=AsyncMock(side_effect=RuntimeError("db is down")))

    with pytest.raises(RuntimeError, match="db is down"):
        await delete_expired_tokens(db)

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


async def test_rolls_back_and_reraises_when_commit_fails():
    db = _fake_db(commit=AsyncMock(side_effect=RuntimeError("commit failed")))

    with pytest.raises(RuntimeError, match="commit failed"):
        await delete_expired_tokens(db)

    db.rollback.assert_awaited_once()


async def test_does_not_roll_back_on_success():
    db = _fake_db()

    await delete_expired_tokens(db)

    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
    assert db.execute.await_count == len(EXPIRING_MODELS)


async def test_none_rowcount_is_reported_as_zero():
    db = _fake_db(execute=AsyncMock(return_value=MagicMock(rowcount=None)))

    result = await delete_expired_tokens(db)

    assert result == {model.__tablename__: 0 for model in token_cleanup.EXPIRING_MODELS}
