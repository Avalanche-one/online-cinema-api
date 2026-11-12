from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DECIMAL,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from online_cinema_api.db.base import Base

if TYPE_CHECKING:
    from online_cinema_api.db.models.accounts import UserModel
    from online_cinema_api.db.models.movies import MovieModel


class OrderStatusEnum(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELED = "canceled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[OrderStatusEnum] = mapped_column(
        Enum(OrderStatusEnum, name="order_status_enum", native_enum=False),
        default=OrderStatusEnum.PENDING,
        nullable=False,
    )
    total_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 2), nullable=True)

    user: Mapped[UserModel] = relationship("UserModel")
    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, user_id={self.user_id}, status={self.status})>"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id"), nullable=False, index=True
    )
    price_at_order: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="items")
    movie: Mapped[MovieModel] = relationship("MovieModel")

    __table_args__ = (
        UniqueConstraint("order_id", "movie_id", name="unique_order_movie_constraint"),
    )

    def __repr__(self) -> str:
        return f"<OrderItem(id={self.id}, order_id={self.order_id}, movie_id={self.movie_id})>"
