from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from online_cinema_api.celery_app import celery_app
from online_cinema_api.core.config import settings
from online_cinema_api.tasks import token_cleanup as tc

TASK_NAME = "tokens.delete_expired_tokens"
SCHEDULE_NAME = "delete-expired-tokens-every-minute"
CLEANUP_RESULT = {"activation": 1, "password_reset": 2, "refresh": 3}


def test_celery_app_basic_config():
    conf = celery_app.conf

    assert celery_app.main == "online_cinema_api"
    assert conf.broker_url == settings.REDIS_URL
    assert conf.timezone == "UTC"
    assert conf.enable_utc is True
    assert conf.task_serializer == "json"
    assert list(conf.accept_content) == ["json"]
    assert conf.task_ignore_result is True
    assert conf.broker_connection_retry_on_startup is True
    assert "online_cinema_api.tasks.token_cleanup" in conf.include


def test_beat_schedule_runs_cleanup_every_minute():
    entry = celery_app.conf.beat_schedule[SCHEDULE_NAME]

    assert entry["task"] == TASK_NAME
    assert entry["schedule"] == 60.0


def test_scheduled_task_is_registered():
    entry = celery_app.conf.beat_schedule[SCHEDULE_NAME]

    assert entry["task"] in celery_app.tasks
    assert celery_app.tasks[TASK_NAME].name == tc.delete_expired_tokens_task.name


def test_task_retry_configuration():
    task = tc.delete_expired_tokens_task

    assert task.name == TASK_NAME
    assert task.autoretry_for == (OperationalError,)
    assert task.retry_kwargs == {"max_retries": 3}
    assert task.retry_backoff is True
    assert task.retry_jitter is True


@pytest.fixture
def cleanup_mocks(monkeypatch):
    engine = MagicMock()
    engine.dispose = AsyncMock()
    create_engine = MagicMock(return_value=engine)

    session = MagicMock()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc_info):
            return False

    factory = MagicMock(return_value=_Ctx())
    make_sessionmaker = MagicMock(return_value=factory)
    delete = AsyncMock(return_value=CLEANUP_RESULT)

    monkeypatch.setattr(tc, "create_async_engine", create_engine)
    monkeypatch.setattr(tc, "async_sessionmaker", make_sessionmaker)
    monkeypatch.setattr(tc, "delete_expired_tokens", delete)

    return {
        "engine": engine,
        "create_engine": create_engine,
        "make_sessionmaker": make_sessionmaker,
        "session": session,
        "delete": delete,
    }


async def test_run_token_cleanup_returns_service_result(cleanup_mocks):
    result = await tc.run_token_cleanup()

    assert result == CLEANUP_RESULT
    cleanup_mocks["delete"].assert_awaited_once_with(cleanup_mocks["session"])


async def test_run_token_cleanup_uses_dedicated_null_pool_engine(cleanup_mocks):
    await tc.run_token_cleanup()

    cleanup_mocks["create_engine"].assert_called_once_with(
        settings.database_url, poolclass=NullPool
    )
    kwargs = cleanup_mocks["make_sessionmaker"].call_args.kwargs
    assert kwargs["bind"] is cleanup_mocks["engine"]
    assert kwargs["expire_on_commit"] is False


async def test_run_token_cleanup_disposes_engine(cleanup_mocks):
    await tc.run_token_cleanup()

    cleanup_mocks["engine"].dispose.assert_awaited_once()


async def test_run_token_cleanup_disposes_engine_on_error(cleanup_mocks):
    cleanup_mocks["delete"].side_effect = RuntimeError("db is down")

    with pytest.raises(RuntimeError, match="db is down"):
        await tc.run_token_cleanup()

    cleanup_mocks["engine"].dispose.assert_awaited_once()


def test_task_runs_cleanup_and_returns_result(monkeypatch):
    run = AsyncMock(return_value=CLEANUP_RESULT)
    monkeypatch.setattr(tc, "run_token_cleanup", run)

    result = tc.delete_expired_tokens_task()

    assert result == CLEANUP_RESULT
    run.assert_awaited_once()


def test_task_propagates_errors(monkeypatch):
    monkeypatch.setattr(
        tc, "run_token_cleanup", AsyncMock(side_effect=ValueError("bad"))
    )

    with pytest.raises(ValueError, match="bad"):
        tc.delete_expired_tokens_task.run()
