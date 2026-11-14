from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.core.exceptions import MovieNotFoundError
from online_cinema_api.core.movie_exceptions import (
    MovieAlreadyInFavoritesError,
    MovieNotInFavoritesError,
)
from online_cinema_api.db.models.movie_interactions import (
    Favorite,
    MovieRating,
    MovieReaction,
    ReactionType,
)
from online_cinema_api.schemas.movie_interactions import MovieStatsSchema
from online_cinema_api.schemas.movies import (
    MovieListItemSchema,
    MovieQueryParams,
    PaginatedResponse,
)
from online_cinema_api.services import movie_catalog
from online_cinema_api.services import movie_interactions as crud


async def ensure_movie_exists(db: AsyncSession, movie_id: int) -> None:
    if not await crud.movie_exists(db, movie_id):
        raise MovieNotFoundError


async def toggle_reaction(
    db: AsyncSession, user_id: int, movie_id: int, reaction: ReactionType
) -> MovieStatsSchema:
    """Та сама реакція вдруге прибирає її, протилежна замінює."""
    await ensure_movie_exists(db, movie_id)

    existing = await crud.get_reaction(db, user_id, movie_id)
    if existing is None:
        db.add(MovieReaction(user_id=user_id, movie_id=movie_id, reaction=reaction))
    elif existing.reaction == reaction:
        await db.delete(existing)
    else:
        existing.reaction = reaction

    try:
        await db.commit()
    except IntegrityError:  # два паралельні запити від одного користувача
        await db.rollback()

    return await crud.get_stats(db, movie_id)


async def set_rating(
    db: AsyncSession, user_id: int, movie_id: int, score: int
) -> MovieStatsSchema:
    await ensure_movie_exists(db, movie_id)

    existing = await crud.get_rating(db, user_id, movie_id)
    if existing is None:
        db.add(MovieRating(user_id=user_id, movie_id=movie_id, score=score))
    else:
        existing.score = score

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()

    return await crud.get_stats(db, movie_id)


async def remove_rating(
    db: AsyncSession, user_id: int, movie_id: int
) -> MovieStatsSchema:
    await ensure_movie_exists(db, movie_id)

    existing = await crud.get_rating(db, user_id, movie_id)
    if existing is not None:
        await db.delete(existing)
        await db.commit()

    return await crud.get_stats(db, movie_id)


async def add_to_favorites(db: AsyncSession, user_id: int, movie_id: int) -> None:
    await ensure_movie_exists(db, movie_id)

    if await crud.get_favorite(db, user_id, movie_id) is not None:
        raise MovieAlreadyInFavoritesError

    db.add(Favorite(user_id=user_id, movie_id=movie_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise MovieAlreadyInFavoritesError


async def remove_from_favorites(db: AsyncSession, user_id: int, movie_id: int) -> None:
    favorite = await crud.get_favorite(db, user_id, movie_id)
    if favorite is None:
        raise MovieNotInFavoritesError
    await db.delete(favorite)
    await db.commit()


async def get_favorites(
    db: AsyncSession, user_id: int, params: MovieQueryParams
) -> PaginatedResponse[MovieListItemSchema]:
    """Обране: той самий пошук, фільтри й сортування, що й у каталозі."""
    return await movie_catalog.get_movies(db, params, favorite_user_id=user_id)
