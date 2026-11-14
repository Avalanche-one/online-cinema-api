from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.core.exceptions import OrderNotFoundError
from online_cinema_api.db.models import OrderStatusEnum
from online_cinema_api.db.models.accounts import (
    UserGroupEnum,
    UserGroupModel,
    UserModel,
)
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies import get_current_user
from online_cinema_api.schemas import UserRead
from online_cinema_api.schemas.orders import (
    OrderCreateResponseSchema,
    OrderListResponseSchema,
    OrderSchema,
)
from online_cinema_api.services import orders as orders_service

router = APIRouter(prefix="/orders", tags=["Orders"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[UserRead, Depends(get_current_user)]


async def _get_own_order(db: AsyncSession, order_id: int, user_id: int):
    order = await orders_service.get_order(db, order_id)
    if order is None or order.user_id != user_id:
        raise OrderNotFoundError
    return order


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def require_staff(db: DbSession, current_user: CurrentUser) -> UserRead:
    group = await db.scalar(
        select(UserGroupModel.name)
        .join(UserModel, UserModel.group_id == UserGroupModel.id)
        .where(UserModel.id == current_user.id)
    )
    if group not in (UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only moderators and admins can view all orders.",
        )
    return current_user


StaffUser = Annotated[UserRead, Depends(require_staff)]


@router.post(
    "",
    response_model=OrderCreateResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create an order from the cart",
    description=(
        "Creates a pending order from the movies in the user's cart. "
        "Movies that were already purchased are skipped. The price of every "
        "movie is saved at the moment of ordering."
    ),
    responses={
        400: {"description": "There are no movies available to order."},
        409: {"description": "A pending order with the same movies already exists."},
    },
)
async def create_order(
    db: DbSession, current_user: CurrentUser
) -> OrderCreateResponseSchema:
    order, removed_movies = await orders_service.create_order_from_cart(
        db, current_user.id
    )
    response = OrderCreateResponseSchema.model_validate(order)
    response.removed_movies = removed_movies
    return response


@router.get(
    "",
    response_model=OrderListResponseSchema,
    summary="List my orders",
    description="Returns the user's orders, newest first, with pagination.",
)
async def list_my_orders(
    db: DbSession,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    per_page: Annotated[int, Query(ge=1, le=20, description="Items per page")] = 10,
) -> OrderListResponseSchema:
    orders, total_items, total_pages = await orders_service.list_orders(
        db, page=page, per_page=per_page, user_id=current_user.id
    )
    return OrderListResponseSchema(
        orders=[OrderSchema.model_validate(order) for order in orders],
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_items=total_items,
    )


@router.get(
    "/all",
    response_model=OrderListResponseSchema,
    summary="List all orders (moderator or admin)",
    description=(
        "Returns orders of all users, newest first. "
        "Can be filtered by user, status and creation date range."
    ),
    responses={403: {"description": "Only moderators and admins can do this."}},
)
async def list_all_orders(
    db: DbSession,
    staff: StaffUser,
    user_id: Annotated[int | None, Query(description="Filter by user id")] = None,
    order_status: Annotated[
        OrderStatusEnum | None, Query(alias="status", description="Filter by status")
    ] = None,
    date_from: Annotated[
        datetime | None, Query(description="Created at or after this date-time")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Created at or before this date-time")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    per_page: Annotated[int, Query(ge=1, le=20, description="Items per page")] = 10,
) -> OrderListResponseSchema:
    orders, total_items, total_pages = await orders_service.list_orders(
        db,
        page=page,
        per_page=per_page,
        user_id=user_id,
        status=order_status,
        date_from=_as_utc(date_from),
        date_to=_as_utc(date_to),
    )
    return OrderListResponseSchema(
        orders=[OrderSchema.model_validate(order) for order in orders],
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_items=total_items,
    )


@router.get(
    "/{order_id}",
    response_model=OrderSchema,
    summary="Get one of my orders",
    responses={404: {"description": "Order not found."}},
)
async def get_my_order(
    order_id: int, db: DbSession, current_user: CurrentUser
) -> OrderSchema:
    order = await _get_own_order(db, order_id, current_user.id)
    return OrderSchema.model_validate(order)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderSchema,
    summary="Cancel a pending order",
    description=(
        "Cancels an order that has not been paid yet. "
        "A paid order can only be canceled through a refund request."
    ),
    responses={
        404: {"description": "Order not found."},
        409: {"description": "The order cannot be canceled in its current status."},
    },
)
async def cancel_my_order(
    order_id: int, db: DbSession, current_user: CurrentUser
) -> OrderSchema:
    order = await _get_own_order(db, order_id, current_user.id)
    order = await orders_service.cancel_order(db, order)
    return OrderSchema.model_validate(order)
