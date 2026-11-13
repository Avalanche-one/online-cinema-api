import asyncio

from celery.utils.log import get_task_logger
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from online_cinema_api.celery_app import celery_app
from online_cinema_api.core.config import settings
from online_cinema_api.services.token_cleanup import (
    delete_expired_activation_tokens,
)

logger = get_task_logger(__name__)


async def run_activation_token_cleanup() -> int:
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    try:
        async with session_factory() as session:
            return await delete_expired_activation_tokens(session)
    finally:
        await engine.dispose()


@celery_app.task(
    name="tokens.delete_expired_activation_tokens",
    autoretry_for=(OperationalError,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_jitter=True,
)
def delete_expired_activation_tokens_task() -> int:
    deleted_count = asyncio.run(run_activation_token_cleanup())

    logger.info(
        "Deleted %s expired activation tokens",
        deleted_count,
    )

    return deleted_count
