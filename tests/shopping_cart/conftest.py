from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from online_cinema_api.db.base import Base
from online_cinema_api.db.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatusEnum,
)
from online_cinema_api.db.models.accounts import (
    UserGroupEnum,
    UserGroupModel,
    UserModel,
    UserProfileModel,
)
from online_cinema_api.db.models.movies import Certification, Movie
from online_cinema_api.db.session import engine, get_db_session
from online_cinema_api.dependencies import get_current_user
from online_cinema_api.dependencies.accounts import required_moderator_or_admin
from online_cinema_api.main import app
from online_cinema_api.schemas.accounts import UserRead


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db_session():
    assert "test" in str(engine.url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def user(db_session):
    group = UserGroupModel(name=UserGroupEnum.ADMIN)
    db_session.add(group)
    await db_session.flush()

    new_user = UserModel.create(
        email="test@example.com", raw_password="Test1234!", group_id=group.id
    )
    new_user.is_active = True
    db_session.add(new_user)
    await db_session.commit()
    return new_user


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(client, user):
    app.dependency_overrides[get_current_user] = lambda: UserRead.model_validate(user)
    app.dependency_overrides[required_moderator_or_admin] = lambda: (
        UserRead.model_validate(user)
    )
    return client


@pytest.fixture
async def movie(db_session):
    cert = Certification(name="PG-13")
    db_session.add(cert)
    await db_session.flush()

    new_movie = Movie(
        name="Test Movie",
        year=2020,
        time=120,
        imdb=7.5,
        votes=1000,
        description="Test description",
        price=Decimal("9.99"),
        certification_id=cert.id,
    )
    db_session.add(new_movie)
    await db_session.commit()
    return new_movie


@pytest.fixture
async def paid_order(db_session, user, movie):
    order = Order(user_id=user.id, status=OrderStatusEnum.PAID)
    db_session.add(order)
    await db_session.flush()
    order_item = OrderItem(
        order_id=order.id, movie_id=movie.id, price_at_order=movie.price
    )
    db_session.add(order_item)
    await db_session.commit()


@pytest.fixture
async def add_movie_in_cart(db_session, user, movie):
    cart = Cart(user_id=user.id)
    db_session.add(cart)
    await db_session.flush()
    cart_item = CartItem(cart_id=cart.id, movie_id=movie.id)
    db_session.add(cart_item)
    await db_session.commit()


@pytest.fixture
async def create_user_profile(db_session, user):
    user_profile = UserProfileModel(date_of_birth=date(2000, 10, 10), user_id=user.id)
    db_session.add(user_profile)
    await db_session.commit()
    return user_profile
