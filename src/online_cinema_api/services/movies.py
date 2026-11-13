from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from online_cinema_api.core.exceptions import MovieNotFoundError
from online_cinema_api.core.movie_exceptions import (
    EntityNotFoundError,
    MovieAlreadyExistsError,
    NameAlreadyExistsError,
)
from online_cinema_api.db.models.movies import (
    Certification,
    Director,
    Genre,
    Movie,
    Star,
)
from online_cinema_api.schemas.movies import NameCreateSchema

NamedModel = type[Genre] | type[Star] | type[Director]


# --- Movie ---


async def get_movie_by_id(db: AsyncSession, movie_id: int) -> Movie:
    movie = await db.scalar(
        select(Movie)
        .where(Movie.id == movie_id)
        .options(
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors),
            selectinload(Movie.certification),
        )
    )
    if movie is None:
        raise MovieNotFoundError
    return movie


async def save_movie(db: AsyncSession, movie: Movie) -> Movie:
    """Зберегти новий або змінений фільм і повернути його з усіма зв'язками."""
    db.add(movie)
    try:
        await db.flush()  # порушення unique (name, year, time) виникає тут
        movie_id = movie.id
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise MovieAlreadyExistsError
    return await get_movie_by_id(db, movie_id)


async def remove_movie(db: AsyncSession, movie: Movie) -> None:
    await db.delete(movie)
    await db.commit()


async def get_certification(
    db: AsyncSession, certification_id: int
) -> Certification | None:
    return await db.get(Certification, certification_id)


async def get_by_ids(db: AsyncSession, model: NamedModel, ids: set[int]) -> list:
    if not ids:
        return []
    return list((await db.scalars(select(model).where(model.id.in_(ids)))).all())


# --- Genre / Star / Director ---


async def list_named(db: AsyncSession, model: NamedModel) -> list:
    return list((await db.scalars(select(model).order_by(model.name))).all())


async def create_named(db: AsyncSession, model: NamedModel, data: NameCreateSchema):
    entity = model(name=data.name)
    db.add(entity)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise NameAlreadyExistsError
    await db.refresh(entity)
    return entity


async def update_named(
    db: AsyncSession, model: NamedModel, entity_id: int, data: NameCreateSchema
):
    entity = await db.get(model, entity_id)
    if entity is None:
        raise EntityNotFoundError
    entity.name = data.name
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise NameAlreadyExistsError
    await db.refresh(entity)
    return entity


async def delete_named(db: AsyncSession, model: NamedModel, entity_id: int) -> None:
    entity = await db.get(model, entity_id)
    if entity is None:
        raise EntityNotFoundError
    await db.delete(entity)
    await db.commit()
