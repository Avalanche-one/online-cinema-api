from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.core.config import Settings, get_settings, settings
from online_cinema_api.core.exceptions import (
    AccountAlreadyActiveError,
    AccountNotActivatedError,
    InvalidActivationTokenError,
    InvalidCredentialsError,
    RefreshTokenNotFoundError,
    UserAlreadyExistsError,
    UserGroupNotFoundError,
    UserNotFoundError,
)
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies import (
    get_accounts_email_notificator,
    get_jwt_auth_manager,
)
from online_cinema_api.dependencies.accounts import required_moderator_or_admin
from online_cinema_api.exceptions import BaseSecurityError
from online_cinema_api.notifications import EmailSenderInterface
from online_cinema_api.schemas import (
    MessageResponseSchema,
    PasswordResetCompleteRequestSchema,
    PasswordResetRequestSchema,
    TokenRefreshRequestSchema,
    TokenRefreshResponseSchema,
    UserActivationRequestSchema,
    UserLoginRequestSchema,
    UserLoginResponseSchema,
    UserRegistrationRequestSchema,
    UserRegistrationResponseSchema,
)
from online_cinema_api.security.interfaces import JWTAuthManagerInterface
from online_cinema_api.services import accounts as accounts_crud

router = APIRouter(tags=["Accounts"])


@router.post(
    "/register/",
    response_model=UserRegistrationResponseSchema,
    summary="User Registration",
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    user_data: UserRegistrationRequestSchema,
    db: AsyncSession = Depends(get_db_session),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> UserRegistrationResponseSchema:
    existing_user = await accounts_crud.get_user_by_email(db, str(user_data.email))
    if existing_user:
        raise UserAlreadyExistsError(
            f"A user with this email {user_data.email} already exists."
        )

    user_group = await accounts_crud.get_default_user_group(db)
    if not user_group:
        raise UserGroupNotFoundError()

    try:
        new_user, activation_token = await accounts_crud.create_user_with_activation(
            db=db,
            email=str(user_data.email),
            raw_password=user_data.password,
            group_id=user_group.id,
        )
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during user creation.",
        ) from e

    activation_link = f"{settings.DOMAIN}/api/v1/accounts/activate/?token={activation_token.token}"
    await email_sender.send_activation_email(new_user.email, activation_link)

    return UserRegistrationResponseSchema.model_validate(new_user)


@router.post(
    "/activate/",
    response_model=MessageResponseSchema,
    summary="Activate User Account",
    status_code=status.HTTP_200_OK,
)
async def activate_account(
    activation_data: UserActivationRequestSchema,
    db: AsyncSession = Depends(get_db_session),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> MessageResponseSchema:
    token_record = await accounts_crud.get_activation_token_with_user(
        db, str(activation_data.email), activation_data.token
    )

    now_utc = datetime.now(UTC)
    if (
        not token_record
        or cast(datetime, token_record.expires_at).replace(tzinfo=UTC) < now_utc
    ):
        if token_record:
            await accounts_crud.delete_token_and_commit(db, token_record)
        raise InvalidActivationTokenError()

    user = token_record.user
    if user.is_active:
        raise AccountAlreadyActiveError()

    await accounts_crud.activate_user_account(db, user, token_record)

    login_link = f"{settings.DOMAIN}/api/v1/accounts/login/"
    await email_sender.send_activation_complete_email(
        str(activation_data.email), login_link
    )

    return MessageResponseSchema(message="User account activated successfully.")


@router.post(
    "/password-reset/request/",
    response_model=MessageResponseSchema,
    summary="Request Password Reset Token",
    status_code=status.HTTP_200_OK,
)
async def request_password_reset_token(
    data: PasswordResetRequestSchema,
    db: AsyncSession = Depends(get_db_session),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> MessageResponseSchema:
    user = await accounts_crud.get_user_by_email(db, str(data.email))

    if not user or not user.is_active:
        return MessageResponseSchema(
            message="If you are registered, you will receive an email with instructions."
        )

    await accounts_crud.recreate_password_reset_token(db, cast(int, user.id))

    password_reset_complete_link = (
        f"{settings.DOMAIN}/api/v1/accounts/password-reset-complete/"
    )
    await email_sender.send_password_reset_email(
        str(data.email), password_reset_complete_link
    )

    return MessageResponseSchema(
        message="If you are registered, you will receive an email with instructions."
    )


@router.post(
    "/reset-password/complete/",
    response_model=MessageResponseSchema,
    summary="Reset User Password",
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    data: PasswordResetCompleteRequestSchema,
    db: AsyncSession = Depends(get_db_session),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> MessageResponseSchema:
    user = await accounts_crud.get_user_by_email(db, str(data.email))
    if not user or not user.is_active:
        raise InvalidActivationTokenError("Invalid email or token.")

    token_record = await accounts_crud.get_password_reset_token(db, user.id)

    if not token_record or token_record.token != data.token:
        if token_record:
            await accounts_crud.delete_token_and_commit(db, token_record)
        raise InvalidActivationTokenError("Invalid email or token.")

    expires_at = cast(datetime, token_record.expires_at).replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        await accounts_crud.delete_token_and_commit(db, token_record)
        raise InvalidActivationTokenError("Invalid email or token.")

    try:
        await accounts_crud.update_password_and_delete_token(
            db, user, data.password, token_record
        )
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting the password.",
        )

    login_link = f"{settings.DOMAIN}/api/v1/accounts/login/"
    await email_sender.send_password_reset_complete_email(str(data.email), login_link)

    return MessageResponseSchema(message="Password reset successfully.")


@router.post(
    "/login/",
    response_model=UserLoginResponseSchema,
    summary="User Login",
    status_code=status.HTTP_201_CREATED,
)
async def login_user(
    login_data: UserLoginRequestSchema,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
) -> UserLoginResponseSchema:
    user = await accounts_crud.get_user_by_email(db, str(login_data.email))

    if not user or not user.verify_password(login_data.password):
        raise InvalidCredentialsError()

    if not user.is_active:
        raise AccountNotActivatedError()

    jwt_refresh_token = jwt_manager.create_refresh_token({"user_id": user.id})

    try:
        await accounts_crud.create_refresh_token_record(
            db=db,
            user_id=cast(int, user.id),
            days_valid=settings.LOGIN_TIME_DAYS,
            token=jwt_refresh_token,
        )
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request.",
        )

    jwt_access_token = jwt_manager.create_access_token({"user_id": user.id})
    return UserLoginResponseSchema(
        access_token=jwt_access_token,
        refresh_token=jwt_refresh_token,
    )


@router.post(
    "/refresh/",
    response_model=TokenRefreshResponseSchema,
    summary="Refresh Access Token",
    status_code=status.HTTP_200_OK,
)
async def refresh_access_token(
    token_data: TokenRefreshRequestSchema,
    db: AsyncSession = Depends(get_db_session),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
) -> TokenRefreshResponseSchema:
    try:
        decoded_token = jwt_manager.decode_refresh_token(token_data.refresh_token)
        user_id = decoded_token.get("user_id")
    except BaseSecurityError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )

    refresh_token_record = await accounts_crud.get_refresh_token_record(
        db, token_data.refresh_token
    )
    if not refresh_token_record:
        raise RefreshTokenNotFoundError()

    user = await accounts_crud.get_user_by_id(db, user_id)
    if not user:
        raise UserNotFoundError()

    new_access_token = jwt_manager.create_access_token({"user_id": user_id})

    return TokenRefreshResponseSchema(access_token=new_access_token)


@router.post(
    "/resend-activation/",
    response_model=MessageResponseSchema,
    summary="Resend Activation Token",
    status_code=status.HTTP_200_OK,
)
async def resend_activation_token(
    data: PasswordResetRequestSchema,
    db: AsyncSession = Depends(get_db_session),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> MessageResponseSchema:
    user = await accounts_crud.get_user_by_email(db, str(data.email))
    if not user or user.is_active:
        return MessageResponseSchema(
            message="If the account exists and is inactive, a new token has been sent."
        )

    await accounts_crud.recreate_activation_token(db, cast(int, user.id))

    activation_link = f"{settings.DOMAIN}/api/v1/accounts/activate/"
    await email_sender.send_activation_email(user.email, activation_link)

    return MessageResponseSchema(message="Activation email resent successfully.")


@router.post(
    "/logout/",
    response_model=MessageResponseSchema,
    summary="User Logout",
    status_code=status.HTTP_200_OK,
)
async def logout_user(
    token_data: TokenRefreshRequestSchema,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponseSchema:
    refresh_token_record = await accounts_crud.get_refresh_token_record(
        db, token_data.refresh_token
    )
    if refresh_token_record:
        await accounts_crud.delete_token_and_commit(db, refresh_token_record)

    return MessageResponseSchema(message="Successfully logged out.")


@router.patch(
    "/admin/users/{user_id}/activate/",
    response_model=MessageResponseSchema,
    summary="Admin Manual User Activation",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(required_moderator_or_admin)],
)
async def admin_activate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponseSchema:
    user = await accounts_crud.get_user_by_id(db, user_id)
    if not user:
        raise UserNotFoundError()

    user.is_active = True
    await db.commit()
    return MessageResponseSchema(
        message=f"User {user.email} has been manually activated."
    )


@router.patch(
    "/admin/users/{user_id}/group/",
    response_model=MessageResponseSchema,
    summary="Admin Change User Group",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(required_moderator_or_admin)],
)
async def admin_change_user_group(
    user_id: int,
    new_group_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponseSchema:
    user = await accounts_crud.get_user_by_id(db, user_id)
    if not user:
        raise UserNotFoundError()

    user.group_id = new_group_id
    await db.commit()
    return MessageResponseSchema(message="User group updated successfully.")
