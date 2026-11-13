from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from online_cinema_api.core.exceptions import (
    MovieExistInCart,
    MovieExistInOrderError,
    MovieNotFoundError,
    MovieNotInCartError,
)
from online_cinema_api.db.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatusEnum,
)
from online_cinema_api.db.models.accounts import UserModel
from online_cinema_api.db.models.movies import Movie
from online_cinema_api.schemas.shopping_cart import CartItemAdd, CartMovieResponse


async def add_movie_to_cart(
    data: CartItemAdd, db: AsyncSession, current_user: UserModel
):
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
        .where(Cart.user_id == current_user.id, CartItem.movie_id == data.movie_id)
        .limit(1)
    )
    if is_movie_in_cart:
        raise MovieExistInCart

    cart_user = await db.scalar(select(Cart).where(Cart.user_id == current_user.id))
    if cart_user is None:
        cart_user = Cart(user_id=current_user.id)
        db.add(cart_user)
        await db.flush()

    item = CartItem(cart_id=cart_user.id, movie_id=data.movie_id)
    db.add(item)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise MovieExistInCart

    await db.refresh(item)
    return item


async def delete_movie_from_cart_by_user_id(
    db: AsyncSession, data_user: UserModel, movie_id: int
):
    movie_for_delete = await db.scalar(
        select(CartItem)
        .join(Cart, CartItem.cart_id == Cart.id)
        .where(Cart.user_id == data_user.id, CartItem.movie_id == movie_id)
    )

    if movie_for_delete is None:
        raise MovieNotInCartError

    await db.delete(movie_for_delete)
    await db.commit()


async def get_movie_from_cart(db: AsyncSession, current_user: UserModel):
    result = (
        await db.scalars(
            select(CartItem)
            .join(Cart, CartItem.cart_id == Cart.id)
            .where(Cart.user_id == current_user.id)
            .options(selectinload(CartItem.movie).selectinload(Movie.genres))
            .order_by(CartItem.added_at)
        )
    ).all()

    movies = []
    total_price = 0
    for item in result:
        movie = item.movie
        movies.append(
            CartMovieResponse(
                id=movie.id,
                name=movie.name,
                price=movie.price,
                year=movie.year,
                genres=[i.name for i in movie.genres],
                added_at=item.added_at,
            )
        )
        total_price += movie.price

    return {"items": movies, "total_price": total_price}


async def delete_all_movie_from_cart(db: AsyncSession, current_user: UserModel):
    query = (
        select(CartItem.id)
        .join(Cart, CartItem.cart_id == Cart.id)
        .where(Cart.user_id == current_user.id)
    )
    delete_query = delete(CartItem).where(CartItem.id.in_(query))
    await db.execute(delete_query)
    await db.commit()
