from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import MovieNotFoundError, MovieExistInOrderError, MovieExistInCart
from db.models import OrderItem, Cart, CartItem, Order, OrderStatusEnum
from db.models.accounts import UserModel
from db.models.movies import Movie
from schemas.shopping_cart import CartItemAdd


async def add_movie_to_cart(data: CartItemAdd, db: AsyncSession, current_user: UserModel):
    movie = await db.scalar(select(Movie).where(Movie.id == data.movie_id))
    if movie is None:
        raise MovieNotFoundError

    is_movie_already_in_order = await db.scalar(
        select(OrderItem.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            Order.user_id == current_user.id,
            Order.status == OrderStatusEnum.PAID,
            OrderItem.movie_id == data.movie_id,
        )
        .limit(1)
    )
    if is_movie_already_in_order:
        raise MovieExistInOrderError

    is_movie_in_cart = await db.scalar(
        select(CartItem.id)
        .join(Cart, CartItem.cart_id == Cart.id)
        .where(
            Cart.user_id == current_user.id,
            CartItem.movie_id == data.movie_id
        )
        .limit(1)
    )
    if is_movie_in_cart:
        raise MovieExistInCart

    cart_user = await db.scalar(select(Cart).where(Cart.user_id == current_user.id))
    if cart_user is None:
        cart_user = Cart(
            user_id=current_user.id
        )
        db.add(cart_user)
        await db.flush()

    item = CartItem(
        cart_id=cart_user.id,
        movie_id=data.movie_id
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise MovieExistInCart


    await db.refresh(item)
    return item

