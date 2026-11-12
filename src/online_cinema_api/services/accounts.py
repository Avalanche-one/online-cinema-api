from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.models.accounts import UserModel


async def create_user(
    db: AsyncSession, email: str, raw_password: str, group_id: int
) -> UserModel:
    db_user = UserModel(email=email, group_id=group_id)
    db_user.password = raw_password

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def get_user_by_email(db: AsyncSession, email: str) -> UserModel | None:
    result = await db.execute(select(UserModel).where(UserModel.email == email))
    return result.scalar_one_or_none()
