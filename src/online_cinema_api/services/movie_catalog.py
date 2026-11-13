from math import ceil

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from online_cinema_api.db.models.movie_interactions import Favorite
from online_cinema_api.db.models.movies import (
    Director,
    Genre,
    Movie,
    Star,
    movie_genres_table,
)
from online_cinema_api.schemas.movies import (
    GenreWithCountSchema,
    MovieListItemSchema,
    MovieQueryParams,
    MovieSortBy,
    PaginatedResponse,
    SortOrder,
)

SORT_COLUMNS = {
    MovieSortBy.NAME: Movie.name,
    MovieSortBy.YEAR: Movie.year,
    MovieSortBy.IMDB: Movie.imdb,
    MovieSortBy.PRICE: Movie.price,
    MovieSortBy.POPULARITY: Movie.votes,
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_conditions(
    params: MovieQueryParams, favorite_user_id: int | None
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    if favorite_user_id is not None:
        conditions.append(
            Movie.id.in_(
                select(Favorite.movie_id).where(Favorite.user_id == favorite_user_id)
            )
        )

    if params.search:
        pattern = f"%{_escape_like(params.search)}%"
        conditions.append(
            or_(
                Movie.name.ilike(pattern, escape="\\"),
                Movie.description.ilike(pattern, escape="\\"),
                Movie.stars.any(Star.name.ilike(pattern, escape="\\")),
                Movie.directors.any(Director.name.ilike(pattern, escape="\\")),
            )
        )

    if params.year_from is not None:
        conditions.append(Movie.year >= params.year_from)
    if params.year_to is not None:
        conditions.append(Movie.year <= params.year_to)
    if params.imdb_min is not None:
        conditions.append(Movie.imdb >= params.imdb_min)
    if params.imdb_max is not None:
        conditions.append(Movie.imdb <= params.imdb_max)
    if params.price_min is not None:
        conditions.append(Movie.price >= params.price_min)
    if params.price_max is not None:
        conditions.append(Movie.price <= params.price_max)

    if params.certification_id is not None:
        conditions.append(Movie.certification_id == params.certification_id)
    if params.genre_id is not None:
        conditions.append(Movie.genres.any(Genre.id == params.genre_id))
    if params.star_id is not None:
        conditions.append(Movie.stars.any(Star.id == params.star_id))
    if params.director_id is not None:
        conditions.append(Movie.directors.any(Director.id == params.director_id))

    return conditions


async def get_movies(
    db: AsyncSession,
    params: MovieQueryParams,
    favorite_user_id: int | None = None,
) -> PaginatedResponse[MovieListItemSchema]:
    """Каталог фільмів. Якщо передано favorite_user_id, то це список обраного."""
    conditions = _build_conditions(params, favorite_user_id)

    total = await db.scalar(select(func.count(Movie.id)).where(*conditions)) or 0

    sort_column = SORT_COLUMNS[params.sort_by]
    direction = (
        sort_column.desc() if params.order == SortOrder.DESC else sort_column.asc()
    )

    movies = (
        await db.scalars(
            select(Movie)
            .where(*conditions)
            .options(selectinload(Movie.genres))
            .order_by(direction, Movie.id)  # Movie.id робить сортування стабільним
            .offset(params.offset)
            .limit(params.per_page)
        )
    ).all()

    return PaginatedResponse[MovieListItemSchema](
        items=[MovieListItemSchema.model_validate(movie) for movie in movies],
        total=total,
        page=params.page,
        per_page=params.per_page,
        pages=ceil(total / params.per_page),
    )


async def get_genres_with_count(db: AsyncSession) -> list[GenreWithCountSchema]:
    rows = await db.execute(
        select(
            Genre.id,
            Genre.name,
            func.count(movie_genres_table.c.movie_id).label("movies_count"),
        )
        .outerjoin(movie_genres_table, movie_genres_table.c.genre_id == Genre.id)
        .group_by(Genre.id, Genre.name)
        .order_by(Genre.name)
    )
    return [
        GenreWithCountSchema(id=row.id, name=row.name, movies_count=row.movies_count)
        for row in rows
    ]
