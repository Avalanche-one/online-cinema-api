from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DECIMAL, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from online_cinema_api.db.base import Base
from online_cinema_api.db.models.accounts import UserModel
from online_cinema_api.db.models.orders import Order, OrderItem


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[PaymentStatus] = mapped_column(
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.name,
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    external_payment_id: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[UserModel] = relationship()
    order: Mapped[Order] = relationship()
    items: Mapped[list[PaymentItemModel]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentItemModel(Base):
    __tablename__ = "payment_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT"), index=True
    )
    price_at_payment: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    payment: Mapped[PaymentModel] = relationship(back_populates="items")
    order_item: Mapped[OrderItem] = relationship()
