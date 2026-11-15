from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.models.accounts import (
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
)

EXPIRING_MODELS = (
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
)


async def delete_expired_tokens(db: AsyncSession) -> dict[str, int]:
    deleted: dict[str, int] = {}
    try:
        for model in EXPIRING_MODELS:
            result = await db.execute(
                delete(model).where(model.expires_at <= func.now())
            )
            deleted[model.__tablename__] = result.rowcount or 0
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return deleted
