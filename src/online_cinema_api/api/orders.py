from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.core.exceptions import OrderNotFoundError
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies import get_current_user
from online_cinema_api.schemas import UserRead
from online_cinema_api.schemas.orders import OrderListResponseSchema, OrderSchema
from online_cinema_api.services import orders as orders_service

router = APIRouter(prefix="/orders", tags=["Orders"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[UserRead, Depends(get_current_user)]


async def _get_own_order(db: AsyncSession, order_id: int, user_id: int):
    order = await orders_service.get_order(db, order_id)
    if order is None or order.user_id != user_id:
        raise OrderNotFoundError
    return order


@router.post(
    "",
    response_model=OrderSchema,
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
async def create_order(db: DbSession, current_user: CurrentUser) -> OrderSchema:
    order = await orders_service.create_order_from_cart(db, current_user.id)
    return OrderSchema.model_validate(order)


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
