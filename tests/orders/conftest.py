import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from online_cinema_api.core.config import settings
from online_cinema_api.db.base import Base
from online_cinema_api.db.models import (
    Cart,
    CartItem,
    Certification,
    Movie,
    Order,
    OrderItem,
    OrderStatusEnum,
    UserGroupModel,
    UserModel,
    UserProfileModel,
)
from online_cinema_api.db.models.accounts import UserGroupEnum
from online_cinema_api.db.session import get_db_session
from online_cinema_api.main import app
from online_cinema_api.security.token_manager import JWTAuthManager

db_engine = create_async_engine(settings.database_url, poolclass=NullPool)

EXCLUDED_TABLES = set()
TABLES = [
    table for table in Base.metadata.sorted_tables if table.name not in EXCLUDED_TABLES
]

CATALOG = {
    "one": ("Test Movie One", "9.99", "PG-13"),
    "two": ("Test Movie Two", "14.50", "PG-13"),
    "adult": ("Adult Movie", "12.00", "R"),
    "kids": ("Kids Movie", "5.00", "PG"),
}


def db_run(callback: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
    async def runner() -> Any:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await callback(session)

    return asyncio.run(runner())


@dataclass
class UserInfo:
    id: int
    email: str
    headers: dict[str, str]


@pytest.fixture(scope="session")
def database() -> None:
    if "test" not in settings.database_url:
        raise RuntimeError("Tests must run against a database with 'test' in its name.")

    async def recreate() -> None:
        async with db_engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.drop_all, tables=list(reversed(TABLES))
            )
            await connection.run_sync(Base.metadata.create_all, tables=TABLES)

    asyncio.run(recreate())


@pytest.fixture(autouse=True)
def movies(database: None) -> dict[str, int]:
    table_names = ", ".join(f'"{table.name}"' for table in TABLES)

    async def reset(session: AsyncSession) -> dict[str, int]:
        await session.execute(
            text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
        )
        session.add_all([UserGroupModel(name=group) for group in UserGroupEnum])
        certifications = {
            name: Certification(name=name) for name in ("PG-13", "R", "PG")
        }
        session.add_all(certifications.values())
        await session.flush()

        created = {}
        for key, (name, price, certification) in CATALOG.items():
            movie = Movie(
                name=name,
                year=2020,
                time=100,
                imdb=7.5,
                votes=1000,
                description="Test movie",
                price=Decimal(price),
                certification_id=certifications[certification].id,
            )
            session.add(movie)
            created[key] = movie
        await session.commit()
        return {key: movie.id for key, movie in created.items()}

    return db_run(reset)


@pytest.fixture
def run_db() -> Callable[[Callable[[AsyncSession], Awaitable[Any]]], Any]:
    return db_run


@pytest.fixture
def client() -> Iterator[TestClient]:
    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user() -> Callable[..., UserInfo]:
    jwt_manager = JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM,
    )

    def create(
        email: str,
        group: UserGroupEnum = UserGroupEnum.USER,
        birth_date: date | None = None,
    ) -> UserInfo:
        async def insert(session: AsyncSession) -> int:
            group_id = await session.scalar(
                select(UserGroupModel.id).where(UserGroupModel.name == group)
            )
            user = UserModel(
                email=email,
                group_id=group_id,
                is_active=True,
                _hashed_password="not-used-in-tests",
            )
            session.add(user)
            await session.flush()
            if birth_date is not None:
                session.add(UserProfileModel(user_id=user.id, date_of_birth=birth_date))
            await session.commit()
            return user.id

        user_id = db_run(insert)
        token = jwt_manager.create_access_token({"sub": email})
        return UserInfo(
            id=user_id, email=email, headers={"Authorization": f"Bearer {token}"}
        )

    return create


@pytest.fixture
def add_to_cart() -> Callable[[int, list[int]], None]:
    def add(user_id: int, movie_ids: list[int]) -> None:
        async def insert(session: AsyncSession) -> None:
            cart = await session.scalar(select(Cart).where(Cart.user_id == user_id))
            if cart is None:
                cart = Cart(user_id=user_id)
                session.add(cart)
                await session.flush()
            for movie_id in movie_ids:
                session.add(CartItem(cart_id=cart.id, movie_id=movie_id))
            await session.commit()

        db_run(insert)

    return add


@pytest.fixture
def make_order() -> Callable[..., int]:
    def create(
        user_id: int,
        movie_ids: list[int],
        status: OrderStatusEnum = OrderStatusEnum.PENDING,
    ) -> int:
        async def insert(session: AsyncSession) -> int:
            movies_in_order = (
                await session.scalars(select(Movie).where(Movie.id.in_(movie_ids)))
            ).all()
            order = Order(
                user_id=user_id,
                status=status,
                total_amount=sum((m.price for m in movies_in_order), Decimal(0)),
                items=[
                    OrderItem(movie_id=m.id, price_at_order=m.price)
                    for m in movies_in_order
                ],
            )
            session.add(order)
            await session.commit()
            return order.id

        return db_run(insert)

    return create


@pytest.fixture
def set_movie_price() -> Callable[[int, str], None]:
    def change(movie_id: int, price: str) -> None:
        async def update(session: AsyncSession) -> None:
            movie = await session.get(Movie, movie_id)
            movie.price = Decimal(price)
            await session.commit()

        db_run(update)

    return change
