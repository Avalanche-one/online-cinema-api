from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.session import get_db_session
from online_cinema_api.schemas.movies import (
    GenreWithCountSchema,
    MovieDetailSchema,
    MovieListItemSchema,
    MovieQueryParams,
    PaginatedResponse,
)
from online_cinema_api.services import movie_catalog
from online_cinema_api.services import movies as movies_crud

router = APIRouter(tags=["movies"])


@router.get(
    "/movies",
    response_model=PaginatedResponse[MovieListItemSchema],
    summary="Browse the movie catalog",
    description=(
        "Paginated catalog with search (title, description, star, director), "
        "filters (year, IMDb, price, genre, certification, star, director) "
        "and sorting. Popularity is based on the number of IMDb votes."
    ),
)
async def list_movies(
    params: Annotated[MovieQueryParams, Query()],
    db: AsyncSession = Depends(get_db_session),
):
    return await movie_catalog.get_movies(db, params)


@router.get(
    "/movies/{movie_id}",
    response_model=MovieDetailSchema,
    summary="Get movie details",
    responses={404: {"description": "Movie not found"}},
)
async def get_movie(
    movie_id: Annotated[int, Path(ge=1)],
    db: AsyncSession = Depends(get_db_session),
):
    return await movies_crud.get_movie_by_id(db, movie_id)


@router.get(
    "/genres",
    response_model=list[GenreWithCountSchema],
    summary="List genres with the number of movies in each",
    description="To see the movies of a genre, call GET /movies?genre_id=<id>.",
)
async def list_genres(db: AsyncSession = Depends(get_db_session)):
    return await movie_catalog.get_genres_with_count(db)
