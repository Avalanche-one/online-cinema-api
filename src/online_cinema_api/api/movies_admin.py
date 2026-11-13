from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.models.movies import Director, Genre, Star
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies.accounts import required_moderator_or_admin
from online_cinema_api.schemas.movies import (
    MovieCreateSchema,
    MovieDetailSchema,
    MovieUpdateSchema,
    NameCreateSchema,
    NamedEntitySchema,
)
from online_cinema_api.services import movie_moderation
from online_cinema_api.services import movies as movies_crud

router = APIRouter(
    prefix="/admin",
    tags=["movies (moderator)"],
    dependencies=[Depends(required_moderator_or_admin)],
)

MovieId = Annotated[int, Path(ge=1)]
NamedModel = type[Genre] | type[Star] | type[Director]


@router.post(
    "/movies",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a movie",
    responses={
        409: {"description": "A movie with the same name, year and duration exists"},
        422: {"description": "Certification, genre, star or director not found"},
    },
)
async def create_movie(
    data: MovieCreateSchema, db: AsyncSession = Depends(get_db_session)
):
    return await movie_moderation.create_movie(db, data)


@router.patch(
    "/movies/{movie_id}",
    response_model=MovieDetailSchema,
    summary="Update a movie (only the sent fields change)",
    responses={404: {"description": "Movie not found"}},
)
async def update_movie(
    movie_id: MovieId,
    data: MovieUpdateSchema,
    db: AsyncSession = Depends(get_db_session),
):
    return await movie_moderation.update_movie(db, movie_id, data)


@router.delete(
    "/movies/{movie_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a movie",
    description=(
        "Refused with 409 if the movie is part of any order. If it is in users' "
        "carts, returns 409 as a warning; repeat with force=true to remove it "
        "from those carts and delete it."
    ),
    responses={
        404: {"description": "Movie not found"},
        409: {"description": "Movie is in orders or in users' carts"},
    },
)
async def delete_movie(
    movie_id: MovieId,
    force: Annotated[bool, Query()] = False,
    db: AsyncSession = Depends(get_db_session),
):
    await movie_moderation.delete_movie(db, movie_id, force)


def _add_named_crud(path: str, model: NamedModel) -> None:
    label = path.rstrip("s")

    @router.get(
        f"/{path}", response_model=list[NamedEntitySchema], summary=f"List {path}"
    )
    async def list_items(db: AsyncSession = Depends(get_db_session)):
        return await movies_crud.list_named(db, model)

    @router.post(
        f"/{path}",
        response_model=NamedEntitySchema,
        status_code=status.HTTP_201_CREATED,
        summary=f"Create a {label}",
    )
    async def create_item(
        data: NameCreateSchema, db: AsyncSession = Depends(get_db_session)
    ):
        return await movies_crud.create_named(db, model, data)

    @router.put(
        f"/{path}/{{entity_id}}",
        response_model=NamedEntitySchema,
        summary=f"Rename a {label}",
    )
    async def update_item(
        entity_id: Annotated[int, Path(ge=1)],
        data: NameCreateSchema,
        db: AsyncSession = Depends(get_db_session),
    ):
        return await movies_crud.update_named(db, model, entity_id, data)

    @router.delete(
        f"/{path}/{{entity_id}}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary=f"Delete a {label}",
    )
    async def delete_item(
        entity_id: Annotated[int, Path(ge=1)],
        db: AsyncSession = Depends(get_db_session),
    ):
        await movies_crud.delete_named(db, model, entity_id)


_add_named_crud("genres", Genre)
_add_named_crud("stars", Star)
_add_named_crud("directors", Director)
