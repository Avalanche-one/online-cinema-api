import pytest

from online_cinema_api.core.exceptions import (
    GetPurchasedMoviesError,
    MovieExistInCart,
    MovieExistInOrderError,
    MovieInAnyCartError,
    MovieNotInAnyCartError,
    MovieNotInCartError,
    RemovePurchasedMoviesError,
    RemoveUnavailableMovies,
)
from online_cinema_api.schemas.shopping_cart import CartItemAdd
from online_cinema_api.services.shopping_cart import (
    add_movie_to_cart,
    delete_all_movie_from_cart,
    delete_movie_from_cart_by_user_id,
    get_movie_from_cart,
    get_purchased_movies,
    is_movie_in_any_cart,
    remove_purchased_movies,
    remove_unavailable_movies,
    see_cart_user_for_admin,
)

pytestmark = pytest.mark.anyio


async def test_add_movie(db_session, user, movie):
    item = await add_movie_to_cart(CartItemAdd(movie_id=movie.id), db_session, user)
    assert item.movie_id == movie.id


async def test_add_movie_twice(db_session, user, movie):
    await add_movie_to_cart(CartItemAdd(movie_id=movie.id), db_session, user)
    with pytest.raises(MovieExistInCart):
        await add_movie_to_cart(CartItemAdd(movie_id=movie.id), db_session, user)


async def test_add_movie_when_order_paid(db_session, user, movie, paid_order):
    with pytest.raises(MovieExistInOrderError):
        await add_movie_to_cart(CartItemAdd(movie_id=movie.id), db_session, user)


async def test_delete_movie_from_cart_id_when_not_in_cart(db_session, user, movie):
    with pytest.raises(MovieNotInCartError):
        await delete_movie_from_cart_by_user_id(db_session, user, movie.id)


async def test_delete_movie_from_cart_id_when_in_cart(
    db_session, user, movie, add_movie_in_cart
):
    await delete_movie_from_cart_by_user_id(db_session, user, movie.id)


async def test_get_movie_from_cart(db_session, user, movie, add_movie_in_cart):
    await get_movie_from_cart(db_session, user.id)


async def test_get_movie_from_cart_when_cart_empty(db_session, user, movie):
    await get_movie_from_cart(db_session, user.id)


async def test_delete_all_movie_from_cart_when_cart_empty(db_session, user):
    await delete_all_movie_from_cart(db_session, user)


async def test_delete_all_movie_from_cart(db_session, user, add_movie_in_cart):
    await delete_all_movie_from_cart(db_session, user)


async def test_see_cart_user_for_admin(db_session, user, add_movie_in_cart):
    await see_cart_user_for_admin(db_session, user.id)


async def test_movie_in_any_cart(db_session, movie, add_movie_in_cart):
    result = await is_movie_in_any_cart(db_session, movie.id)
    if result is True:
        pass
    else:
        raise MovieInAnyCartError


async def test_movie_not_in_any_cart(db_session, movie):
    result = await is_movie_in_any_cart(db_session, movie.id)
    if result is False:
        pass
    else:
        raise MovieNotInAnyCartError


async def test_remove_purchased_movies(db_session, user, paid_order, add_movie_in_cart):
    result = await remove_purchased_movies(db_session, user.id)
    if result[0] == "Test Movie":
        pass
    else:
        raise RemovePurchasedMoviesError


async def test_remove_unavailable_movies(
    db_session, movie, user, add_movie_in_cart, create_user_profile
):
    result = await remove_unavailable_movies(db_session, user.id)
    if not result:
        pass
    else:
        raise RemoveUnavailableMovies


async def test_get_purchased_movies(db_session, user, add_movie_in_cart, paid_order):
    result = await get_purchased_movies(db_session, user.id, 10, 0)
    if result[0].name == "Test Movie":
        pass
    else:
        raise GetPurchasedMoviesError
