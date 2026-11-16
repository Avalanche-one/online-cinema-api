import asyncio
import itertools
from decimal import Decimal
from functools import lru_cache

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import online_cinema_api.db.models  # noqa: F401
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
)
from online_cinema_api.db.models.accounts import UserGroupEnum
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies.accounts import get_current_user
from online_cinema_api.main import app
from online_cinema_api.schemas import UserRead
from online_cinema_api.security.passwords import hash_password

PASSWORD = "Str0ng@Passw0rd"


@lru_cache(maxsize=1)
def _password_hash() -> str:
    return hash_password(PASSWORD)


def _test_db_url():
    url = make_url(settings.database_url)
    base = url.database.removesuffix("_test")
    return url.set(database=f"{base}_movies_test")


async def _ensure_database(url) -> None:
    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "select 1 from pg_database where datname = $1", url.database
        )
        if not exists:
            await conn.execute(f'create database "{url.database}"')
    finally:
        await conn.close()


async def _prepare_database(url) -> None:
    await _ensure_database(url)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        async with AsyncSession(engine) as session:
            session.add_all([UserGroupModel(name=group) for group in UserGroupEnum])
            session.add_all(
                [Certification(name=name) for name in ("G", "PG", "PG-13", "R")]
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def test_db_url():
    url = _test_db_url()
    asyncio.run(_prepare_database(url))
    return url


@pytest_asyncio.fixture
async def db(test_db_url):
    engine = create_async_engine(test_db_url, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    async def override_db():
        yield db

    app.dependency_overrides[get_db_session] = override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test/api/v1"
    ) as http_client:
        yield http_client
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def act_as():

    def _act_as(user: UserModel | None) -> None:
        if user is None:
            app.dependency_overrides.pop(get_current_user, None)
            return
        current = UserRead.model_validate(user)
        app.dependency_overrides[get_current_user] = lambda: current

    yield _act_as
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def make_user(db):
    async def _make(email: str, group: UserGroupEnum = UserGroupEnum.USER) -> UserModel:
        group_id = await db.scalar(
            select(UserGroupModel.id).where(UserGroupModel.name == group)
        )
        user = UserModel(email=email, group_id=group_id)
        user._hashed_password = _password_hash()
        user.is_active = True
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user

    return _make


@pytest_asyncio.fixture
async def user(make_user):
    return await make_user("user@example.com")


@pytest_asyncio.fixture
async def other_user(make_user):
    return await make_user("other@example.com")


@pytest_asyncio.fixture
async def moderator(make_user):
    return await make_user("moderator@example.com", UserGroupEnum.MODERATOR)


@pytest_asyncio.fixture
async def admin(make_user):
    return await make_user("admin@example.com", UserGroupEnum.ADMIN)


@pytest_asyncio.fixture
async def certification(db):
    return await db.scalar(select(Certification).order_by(Certification.id).limit(1))


@pytest_asyncio.fixture
async def make_entity(db):

    async def _make(model, name: str):
        entity = model(name=name)
        db.add(entity)
        await db.flush()
        return entity

    return _make


@pytest_asyncio.fixture
async def make_movie(db, certification):
    counter = itertools.count(1)

    async def _make(**overrides) -> Movie:
        n = next(counter)
        data = {
            "name": f"Movie {n}",
            "year": 2000 + n,
            "time": 100 + n,
            "imdb": 5.0,
            "votes": 100,
            "description": f"Description {n}",
            "price": Decimal("9.99"),
            "certification_id": certification.id,
            "genres": [],
            "stars": [],
            "directors": [],
        }
        data.update(overrides)
        movie = Movie(**data)
        db.add(movie)
        await db.flush()
        return movie

    return _make


@pytest_asyncio.fixture
async def movie_payload(db):
    certification = await db.scalar(
        select(Certification).order_by(Certification.id).limit(1)
    )
    cert_id = certification.id if certification else 1

    def _payload(**overrides) -> dict:
        data = {
            "name": "New Movie",
            "year": 2021,
            "time": 110,
            "imdb": 7.5,
            "votes": 500,
            "description": "A new movie",
            "price": "9.99",
            "certification_id": cert_id,
            "genre_ids": [],
            "star_ids": [],
            "director_ids": [],
        }
        data.update(overrides)
        return data

    return _payload


@pytest_asyncio.fixture
async def add_to_cart(db):
    async def _add(user: UserModel, movie: Movie) -> None:
        cart = await db.scalar(select(Cart).where(Cart.user_id == user.id))
        if cart is None:
            cart = Cart(user_id=user.id)
            db.add(cart)
            await db.flush()
        db.add(CartItem(cart_id=cart.id, movie_id=movie.id))
        await db.flush()

    return _add


@pytest_asyncio.fixture
async def add_to_order(db):
    async def _add(
        user: UserModel,
        movie: Movie,
        status: OrderStatusEnum = OrderStatusEnum.PAID,
    ) -> None:
        order = Order(user_id=user.id, status=status, total_amount=movie.price)
        db.add(order)
        await db.flush()
        db.add(
            OrderItem(order_id=order.id, movie_id=movie.id, price_at_order=movie.price)
        )
        await db.flush()

    return _add
