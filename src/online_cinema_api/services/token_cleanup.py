from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.models.accounts import ActivationTokenModel


async def delete_expired_activation_tokens(
    db: AsyncSession,
) -> int:
    try:
        result = await db.execute(
            delete(ActivationTokenModel).where(
                ActivationTokenModel.expires_at <= func.now()
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return result.rowcount or 0
