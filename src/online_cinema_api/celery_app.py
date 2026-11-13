from celery import Celery
from celery.schedules import crontab

from online_cinema_api.core.config import settings

celery_app = Celery(
    "online_cinema_api",
    broker=settings.REDIS_URL,
    include=[
        "online_cinema_api.tasks.token_cleanup",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "delete-expired-activation-tokens-hourly": {
            "task": "tokens.delete_expired_activation_tokens",
            "schedule": crontab(minute=0),
        },
    },
)
