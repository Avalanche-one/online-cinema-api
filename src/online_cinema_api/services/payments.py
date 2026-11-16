import math
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from online_cinema_api.db.models import (
    Order,
    OrderItem,
    OrderStatusEnum,
    PaymentItemModel,
    PaymentModel,
    PaymentStatus,
)
from online_cinema_api.services.shopping_cart import remove_purchased_movies

_PAYMENT_LOAD_OPTIONS = (
    selectinload(PaymentModel.items)
    .selectinload(PaymentItemModel.order_item)
    .selectinload(OrderItem.movie),
)


def to_cents(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def get_payment(db: AsyncSession, payment_id: int) -> PaymentModel | None:
    result = await db.execute(
        select(PaymentModel)
        .options(*_PAYMENT_LOAD_OPTIONS, selectinload(PaymentModel.user))
        .where(PaymentModel.id == payment_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def create_pending_payment(
    db: AsyncSession, order: Order, user_id: int
) -> PaymentModel:
    """Create a pending payment with one PaymentItem per order item.

    The order must be revalidated beforehand, so prices are up to date.
    """
    payment = PaymentModel(
        user_id=user_id,
        order_id=order.id,
        amount=order.total_amount,
        status=PaymentStatus.PENDING,
        items=[
            PaymentItemModel(
                order_item_id=item.id, price_at_payment=item.price_at_order
            )
            for item in order.items
        ],
    )
    db.add(payment)
    await db.commit()
    return await get_payment(db, payment.id)


async def set_external_payment_id(
    db: AsyncSession, payment: PaymentModel, external_payment_id: str
) -> None:
    payment.external_payment_id = external_payment_id
    await db.commit()


async def cancel_payment(db: AsyncSession, payment: PaymentModel) -> None:
    payment.status = PaymentStatus.CANCELED
    await db.commit()


async def complete_payment(
    db: AsyncSession, payment: PaymentModel, payment_intent_id: str | None
) -> None:
    """Mark payment successful, order paid and drop purchased movies from the cart."""
    payment.status = PaymentStatus.SUCCESSFUL
    if payment_intent_id:
        payment.external_payment_id = payment_intent_id

    order = await db.get(Order, payment.order_id)
    order.status = OrderStatusEnum.PAID
    await db.commit()

    await remove_purchased_movies(db, payment.user_id)


async def mark_refunded(db: AsyncSession, payment_intent_id: str) -> None:
    """Mark payment refunded and cancel its order, so movies are no longer owned."""
    payment = await db.scalar(
        select(PaymentModel).where(
            PaymentModel.external_payment_id == payment_intent_id
        )
    )
    if payment:
        payment.status = PaymentStatus.REFUNDED
        order = await db.get(Order, payment.order_id)
        order.status = OrderStatusEnum.CANCELED
        await db.commit()


async def list_payments(
    db: AsyncSession,
    *,
    page: int,
    per_page: int,
    user_id: int | None = None,
    status: PaymentStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[PaymentModel], int, int]:
    conditions = []
    if user_id is not None:
        conditions.append(PaymentModel.user_id == user_id)
    if status is not None:
        conditions.append(PaymentModel.status == status)
    if date_from is not None:
        conditions.append(PaymentModel.created_at >= date_from)
    if date_to is not None:
        conditions.append(PaymentModel.created_at <= date_to)

    total_items = (
        await db.scalar(
            select(func.count()).select_from(PaymentModel).where(*conditions)
        )
        or 0
    )
    total_pages = math.ceil(total_items / per_page)

    result = await db.execute(
        select(PaymentModel)
        .options(*_PAYMENT_LOAD_OPTIONS)
        .where(*conditions)
        .order_by(PaymentModel.created_at.desc(), PaymentModel.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return list(result.scalars().all()), total_items, total_pages
