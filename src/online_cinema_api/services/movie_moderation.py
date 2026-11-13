from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.core.exceptions import MovieInUserCartsError
from online_cinema_api.core.movie_exceptions import (
    MovieHasOrdersError,
    RelatedEntitiesNotFoundError,
)
from online_cinema_api.db.models import CartItem, OrderItem
from online_cinema_api.db.models.movies import Director, Genre, Movie, Star
from online_cinema_api.schemas.movies import MovieCreateSchema, MovieUpdateSchema
from online_cinema_api.services import movies as movies_crud
from online_cinema_api.services.shopping_cart import is_movie_in_any_cart

RELATIONS = {
    "genre_ids": ("genres", Genre),
    "star_ids": ("stars", Star),
    "director_ids": ("directors", Director),
}
NULLABLE_FIELDS = {"meta_score", "gross"}


async def _load_related(
    db: AsyncSession, model: type[Genre | Star | Director], ids: list[int]
) -> list:
    unique_ids = set(ids)
    items = await movies_crud.get_by_ids(db, model, unique_ids)
    if len(items) != len(unique_ids):
        raise RelatedEntitiesNotFoundError
    return items


async def _movie_has_orders(db: AsyncSession, movie_id: int) -> bool:
    # order_items.movie_id без CASCADE, тож блокує замовлення з будь-яким статусом
    found = await db.scalar(
        select(OrderItem.id).where(OrderItem.movie_id == movie_id).limit(1)
    )
    return found is not None


async def create_movie(db: AsyncSession, data: MovieCreateSchema) -> Movie:
    if await movies_crud.get_certification(db, data.certification_id) is None:
        raise RelatedEntitiesNotFoundError

    movie = Movie(
        **data.model_dump(exclude=set(RELATIONS)),
        genres=await _load_related(db, Genre, data.genre_ids),
        stars=await _load_related(db, Star, data.star_ids),
        directors=await _load_related(db, Director, data.director_ids),
    )
    return await movies_crud.save_movie(db, movie)


async def update_movie(
    db: AsyncSession, movie_id: int, data: MovieUpdateSchema
) -> Movie:
    movie = await movies_crud.get_movie_by_id(db, movie_id)

    changes = {
        key: value
        for key, value in data.model_dump(exclude_unset=True).items()
        if value is not None or key in NULLABLE_FIELDS
    }

    for key, (attr, model) in RELATIONS.items():
        ids = changes.pop(key, None)
        if ids is not None:
            setattr(movie, attr, await _load_related(db, model, ids))

    certification_id = changes.get("certification_id")
    if (
        certification_id is not None
        and await movies_crud.get_certification(db, certification_id) is None
    ):
        raise RelatedEntitiesNotFoundError

    for field, value in changes.items():
        setattr(movie, field, value)

    return await movies_crud.save_movie(db, movie)


async def delete_movie(db: AsyncSession, movie_id: int, force: bool = False) -> None:
    movie = await movies_crud.get_movie_by_id(db, movie_id)

    if await _movie_has_orders(db, movie_id):
        raise MovieHasOrdersError

    if await is_movie_in_any_cart(db, movie_id):
        if not force:
            raise MovieInUserCartsError
        # без commit: видалення з кошиків і самого фільму відбудеться однією транзакцією
        await db.execute(delete(CartItem).where(CartItem.movie_id == movie_id))

    await movies_crud.remove_movie(db, movie)
