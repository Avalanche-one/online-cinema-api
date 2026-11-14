import math
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from online_cinema_api.core.exceptions import (
    EmptyOrderError,
    OrderCancellationError,
    OrderNotPendingError,
    PendingOrderExistsError,
)
from online_cinema_api.db.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatusEnum,
)
from online_cinema_api.db.models.movies import Movie


async def get_order(db: AsyncSession, order_id: int) -> Order | None:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.movie))
        .where(Order.id == order_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def list_orders(
    db: AsyncSession,
    *,
    page: int,
    per_page: int,
    user_id: int | None = None,
    status: OrderStatusEnum | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[Order], int, int]:
    conditions = []
    if user_id is not None:
        conditions.append(Order.user_id == user_id)
    if status is not None:
        conditions.append(Order.status == status)
    if date_from is not None:
        conditions.append(Order.created_at >= date_from)
    if date_to is not None:
        conditions.append(Order.created_at <= date_to)

    total_items = await db.scalar(
        select(func.count()).select_from(Order).where(*conditions)
    )
    total_items = total_items or 0
    total_pages = math.ceil(total_items / per_page)

    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.movie))
        .where(*conditions)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return list(result.scalars().all()), total_items, total_pages


async def get_purchased_movie_ids(db: AsyncSession, user_id: int) -> set[int]:
    result = await db.execute(
        select(OrderItem.movie_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.user_id == user_id, Order.status == OrderStatusEnum.PAID)
    )
    return set(result.scalars().all())


async def get_pending_movie_ids(db: AsyncSession, user_id: int) -> set[int]:
    result = await db.execute(
        select(OrderItem.movie_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.user_id == user_id, Order.status == OrderStatusEnum.PENDING)
    )
    return set(result.scalars().all())


async def is_movie_purchased(db: AsyncSession, movie_id: int) -> bool:
    result = await db.execute(
        select(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.movie_id == movie_id, Order.status == OrderStatusEnum.PAID)
        .limit(1)
    )
    return result.first() is not None


async def create_order_from_cart(db: AsyncSession, user_id: int) -> Order:
    cart_items = (
        await db.scalars(
            select(CartItem)
            .join(Cart, CartItem.cart_id == Cart.id)
            .where(Cart.user_id == user_id)
            .options(selectinload(CartItem.movie))
            .order_by(CartItem.added_at)
        )
    ).all()

    purchased_ids = await get_purchased_movie_ids(db, user_id)
    items_to_order = [item for item in cart_items if item.movie_id not in purchased_ids]
    if not items_to_order:
        raise EmptyOrderError

    pending_ids = await get_pending_movie_ids(db, user_id)
    if any(item.movie_id in pending_ids for item in items_to_order):
        raise PendingOrderExistsError

    order = Order(
        user_id=user_id,
        status=OrderStatusEnum.PENDING,
        total_amount=sum((item.movie.price for item in items_to_order), Decimal(0)),
        items=[
            OrderItem(movie_id=item.movie_id, price_at_order=item.movie.price)
            for item in items_to_order
        ],
    )
    db.add(order)
    await db.commit()
    return await get_order(db, order.id)


async def cancel_order(db: AsyncSession, order: Order) -> Order:
    if order.status == OrderStatusEnum.PAID:
        raise OrderCancellationError(
            "A paid order can only be canceled through a refund request."
        )
    if order.status == OrderStatusEnum.CANCELED:
        raise OrderCancellationError("The order is already canceled.")

    order.status = OrderStatusEnum.CANCELED
    await db.commit()
    return await get_order(db, order.id)


async def revalidate_order_total(db: AsyncSession, order: Order) -> Order:
    """Refresh the prices of a pending order from the current movie prices.

    Must be called right before creating the payment, because movie prices
    can change after the order was created.
    """
    if order.status != OrderStatusEnum.PENDING:
        raise OrderNotPendingError

    movies = (
        await db.scalars(
            select(Movie).where(Movie.id.in_([item.movie_id for item in order.items]))
        )
    ).all()
    current_prices = {movie.id: movie.price for movie in movies}

    for item in order.items:
        item.price_at_order = current_prices[item.movie_id]
    order.total_amount = sum((item.price_at_order for item in order.items), Decimal(0))
    await db.commit()
    return await get_order(db, order.id)
