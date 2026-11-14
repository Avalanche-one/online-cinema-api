from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.models.movie_interactions import (
    Favorite,
    MovieRating,
    MovieReaction,
    ReactionType,
)
from online_cinema_api.db.models.movies import Movie
from online_cinema_api.schemas.movie_interactions import MovieStatsSchema


async def movie_exists(db: AsyncSession, movie_id: int) -> bool:
    return await db.scalar(select(Movie.id).where(Movie.id == movie_id)) is not None


async def get_reaction(
    db: AsyncSession, user_id: int, movie_id: int
) -> MovieReaction | None:
    return await db.scalar(
        select(MovieReaction).where(
            MovieReaction.user_id == user_id, MovieReaction.movie_id == movie_id
        )
    )


async def get_rating(
    db: AsyncSession, user_id: int, movie_id: int
) -> MovieRating | None:
    return await db.scalar(
        select(MovieRating).where(
            MovieRating.user_id == user_id, MovieRating.movie_id == movie_id
        )
    )


async def get_favorite(
    db: AsyncSession, user_id: int, movie_id: int
) -> Favorite | None:
    return await db.scalar(
        select(Favorite).where(
            Favorite.user_id == user_id, Favorite.movie_id == movie_id
        )
    )


async def get_stats(db: AsyncSession, movie_id: int) -> MovieStatsSchema:
    reaction_rows = await db.execute(
        select(MovieReaction.reaction, func.count())
        .where(MovieReaction.movie_id == movie_id)
        .group_by(MovieReaction.reaction)
    )
    counts = {reaction: count for reaction, count in reaction_rows}

    rating_avg, ratings_count = (
        await db.execute(
            select(func.avg(MovieRating.score), func.count(MovieRating.id)).where(
                MovieRating.movie_id == movie_id
            )
        )
    ).one()

    return MovieStatsSchema(
        likes=counts.get(ReactionType.LIKE, 0),
        dislikes=counts.get(ReactionType.DISLIKE, 0),
        rating_avg=round(float(rating_avg), 2) if rating_avg is not None else None,
        ratings_count=ratings_count,
    )
