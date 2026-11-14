from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies.accounts import get_current_user
from online_cinema_api.schemas import UserRead
from online_cinema_api.schemas.movie_interactions import (
    MovieStatsSchema,
    RatingRequest,
    ReactionRequest,
)
from online_cinema_api.schemas.movies import (
    MovieListItemSchema,
    MovieQueryParams,
    PaginatedResponse,
)
from online_cinema_api.services import movie_engagement
from online_cinema_api.services import movie_interactions as crud

router = APIRouter(tags=["movie interactions"])

MovieId = Annotated[int, Path(ge=1)]


@router.get(
    "/movies/{movie_id}/stats",
    response_model=MovieStatsSchema,
    summary="Likes, dislikes and average user rating of a movie",
    responses={404: {"description": "Movie not found"}},
)
async def movie_stats(movie_id: MovieId, db: AsyncSession = Depends(get_db_session)):
    await movie_engagement.ensure_movie_exists(db, movie_id)
    return await crud.get_stats(db, movie_id)


@router.post(
    "/movies/{movie_id}/reaction",
    response_model=MovieStatsSchema,
    summary="Like or dislike a movie",
    description=(
        "Sending the same reaction again removes it; sending the opposite one "
        "replaces it."
    ),
    responses={404: {"description": "Movie not found"}},
)
async def react_to_movie(
    movie_id: MovieId,
    data: ReactionRequest,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await movie_engagement.toggle_reaction(
        db, current_user.id, movie_id, data.reaction
    )


@router.put(
    "/movies/{movie_id}/rating",
    response_model=MovieStatsSchema,
    summary="Rate a movie from 1 to 10 (replaces the previous rating)",
    responses={404: {"description": "Movie not found"}},
)
async def rate_movie(
    movie_id: MovieId,
    data: RatingRequest,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await movie_engagement.set_rating(db, current_user.id, movie_id, data.score)


@router.delete(
    "/movies/{movie_id}/rating",
    response_model=MovieStatsSchema,
    summary="Remove your rating of a movie",
    responses={404: {"description": "Movie not found"}},
)
async def delete_movie_rating(
    movie_id: MovieId,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await movie_engagement.remove_rating(db, current_user.id, movie_id)


@router.get(
    "/favorites",
    response_model=PaginatedResponse[MovieListItemSchema],
    summary="List favorite movies",
    description="Supports the same search, filters, sorting and pagination as /movies.",
)
async def list_favorites(
    params: Annotated[MovieQueryParams, Query()],
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await movie_engagement.get_favorites(db, current_user.id, params)


@router.post(
    "/favorites/{movie_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Add a movie to favorites",
    responses={
        404: {"description": "Movie not found"},
        409: {"description": "Already in favorites"},
    },
)
async def add_favorite(
    movie_id: MovieId,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await movie_engagement.add_to_favorites(db, current_user.id, movie_id)


@router.delete(
    "/favorites/{movie_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a movie from favorites",
    responses={404: {"description": "Movie not in favorites"}},
)
async def remove_favorite(
    movie_id: MovieId,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await movie_engagement.remove_from_favorites(db, current_user.id, movie_id)
