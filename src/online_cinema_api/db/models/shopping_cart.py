from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from online_cinema_api.db.base import Base
from online_cinema_api.db.models.movies import Movie


class Cart(Base):
    __tablename__ = "carts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    cart_item: Mapped[list[CartItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    cart_id: Mapped[int] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    cart: Mapped[Cart] = relationship(back_populates="cart_item")
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), nullable=False)
    movie: Mapped[Movie] = relationship()

    __table_args__ = (UniqueConstraint("cart_id", "movie_id"),)
