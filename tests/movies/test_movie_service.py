import pytest

from online_cinema_api.core.exceptions import MovieInUserCartsError, MovieNotFoundError
from online_cinema_api.core.movie_exceptions import (
    MovieAlreadyInFavoritesError,
    MovieHasOrdersError,
    MovieNotInFavoritesError,
)
from online_cinema_api.db.models.movie_interactions import ReactionType
from online_cinema_api.schemas.movies import MovieQueryParams
from online_cinema_api.services import movie_catalog, movie_engagement, movie_moderation
from online_cinema_api.services import movies as movies_crud

pytestmark = pytest.mark.asyncio


async def test_get_movie_by_id_raises_for_missing(db):
    with pytest.raises(MovieNotFoundError):
        await movies_crud.get_movie_by_id(db, 999999)


async def test_catalog_returns_only_favorites_when_user_is_given(db, user, make_movie):
    liked = await make_movie(name="Liked")
    await make_movie(name="Other")
    await movie_engagement.add_to_favorites(db, user.id, liked.id)

    favorites = await movie_catalog.get_movies(
        db, MovieQueryParams(), favorite_user_id=user.id
    )
    assert [movie.name for movie in favorites.items] == ["Liked"]
    assert favorites.total == 1
    assert (await movie_catalog.get_movies(db, MovieQueryParams())).total == 2


async def test_favorites_rules(db, user, make_movie):
    movie = await make_movie()
    with pytest.raises(MovieNotInFavoritesError):
        await movie_engagement.remove_from_favorites(db, user.id, movie.id)

    await movie_engagement.add_to_favorites(db, user.id, movie.id)
    with pytest.raises(MovieAlreadyInFavoritesError):
        await movie_engagement.add_to_favorites(db, user.id, movie.id)
    with pytest.raises(MovieNotFoundError):
        await movie_engagement.add_to_favorites(db, user.id, 999999)


async def test_reaction_counts(db, user, other_user, make_movie):
    movie = await make_movie()
    stats = await movie_engagement.toggle_reaction(
        db, user.id, movie.id, ReactionType.LIKE
    )
    assert (stats.likes, stats.dislikes) == (1, 0)

    stats = await movie_engagement.toggle_reaction(
        db, other_user.id, movie.id, ReactionType.DISLIKE
    )
    assert (stats.likes, stats.dislikes) == (1, 1)

    with pytest.raises(MovieNotFoundError):
        await movie_engagement.toggle_reaction(db, user.id, 999999, ReactionType.LIKE)


async def test_delete_movie_rules(db, user, make_movie, add_to_cart, add_to_order):
    in_cart = await make_movie()
    in_order = await make_movie()
    in_cart_id, in_order_id = in_cart.id, in_order.id
    await add_to_cart(user, in_cart)
    await add_to_order(user, in_order)

    with pytest.raises(MovieInUserCartsError):
        await movie_moderation.delete_movie(db, in_cart_id)
    with pytest.raises(MovieHasOrdersError):
        await movie_moderation.delete_movie(db, in_order_id, force=True)

    await movie_moderation.delete_movie(db, in_cart_id, force=True)
    with pytest.raises(MovieNotFoundError):
        await movies_crud.get_movie_by_id(db, in_cart_id)
