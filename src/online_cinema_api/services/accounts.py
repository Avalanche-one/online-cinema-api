from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from online_cinema_api.db.models.accounts import (
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
)


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
    stmt = select(UserModel).where(UserModel.email == email)
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_default_user_group(db: AsyncSession) -> UserGroupModel | None:
    stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.USER)
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_user_with_activation(
    db: AsyncSession, email: str, raw_password: str, group_id: int
) -> tuple[UserModel, ActivationTokenModel]:
    try:
        new_user = UserModel.create(
            email=email,
            raw_password=raw_password,
            group_id=group_id,
        )
        db.add(new_user)
        await db.flush()

        activation_token = ActivationTokenModel(user_id=new_user.id)
        db.add(activation_token)

        await db.commit()
        await db.refresh(new_user)
        return new_user, activation_token
    except SQLAlchemyError:
        await db.rollback()
        raise


async def get_activation_token_with_user(
    db: AsyncSession, email: str, token: str
) -> ActivationTokenModel | None:
    stmt = (
        select(ActivationTokenModel)
        .options(joinedload(ActivationTokenModel.user))
        .join(UserModel)
        .where(
            UserModel.email == email,
            ActivationTokenModel.token == token,
        )
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def delete_token_and_commit(db: AsyncSession, token_record) -> None:
    await db.delete(token_record)
    await db.commit()


async def activate_user_account(
    db: AsyncSession, user: UserModel, token_record
) -> None:
    user.is_active = True
    await db.delete(token_record)
    await db.commit()


async def recreate_password_reset_token(
    db: AsyncSession, user_id: int
) -> PasswordResetTokenModel:
    await db.execute(
        delete(PasswordResetTokenModel).where(
            PasswordResetTokenModel.user_id == user_id
        )
    )
    reset_token = PasswordResetTokenModel(user_id=user_id)
    db.add(reset_token)
    await db.commit()
    return reset_token


async def get_password_reset_token(
    db: AsyncSession, user_id: int
) -> PasswordResetTokenModel | None:
    stmt = select(PasswordResetTokenModel).filter_by(user_id=user_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def update_password_and_delete_token(
    db: AsyncSession, user: UserModel, new_password: str, token_record
) -> None:
    try:
        user.password = new_password
        await db.delete(token_record)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise


async def create_refresh_token_record(
    db: AsyncSession, user_id: int, days_valid: int, token: str
) -> RefreshTokenModel:
    try:
        refresh_token = RefreshTokenModel.create(
            user_id=user_id,
            days_valid=days_valid,
            token=token,
        )
        db.add(refresh_token)
        await db.flush()
        await db.commit()
        return refresh_token
    except SQLAlchemyError:
        await db.rollback()
        raise


async def get_refresh_token_record(
    db: AsyncSession, token: str
) -> RefreshTokenModel | None:
    stmt = select(RefreshTokenModel).filter_by(token=token)
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_user_by_id(db: AsyncSession, user_id: int) -> UserModel | None:
    stmt = select(UserModel).filter_by(id=user_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def recreate_activation_token(
    db: AsyncSession, user_id: int
) -> ActivationTokenModel:
    await db.execute(
        delete(ActivationTokenModel).where(ActivationTokenModel.user_id == user_id)
    )
    activation_token = ActivationTokenModel(user_id=user_id)
    db.add(activation_token)
    await db.commit()
    return activation_token

async def get_activation_token_by_token(db: AsyncSession, token: str) -> ActivationTokenModel | None:
    """
    Шукає запис активаційного токена за самим токеном разом із пов'язаним користувачем.
    """
    stmt = (
        select(ActivationTokenModel)
        .options(joinedload(ActivationTokenModel.user))
        .where(ActivationTokenModel.token == token)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()