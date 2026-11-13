"""Minimal fixture for manual API testing.

Loads (idempotently):
  * user groups: user / moderator / admin
  * active user  test@example.com / Test1234!
  * 1 certification, 2 genres, 1 director, 1 star
  * 3 movies
  * 1 PENDING order with 2 movies (for POST /api/v1/checkout/{order_id})

Prints an access token, since there is no login endpoint yet.

Usage:
    uv run python scripts/seed_minimal.py
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from online_cinema_api.core.config import get_settings
from online_cinema_api.db.models import (
    Certification,
    Director,
    Genre,
    Movie,
    Order,
    OrderItem,
    OrderStatusEnum,
    Star,
    UserGroupModel,
    UserModel,
)
from online_cinema_api.db.models.accounts import UserGroupEnum
from online_cinema_api.db.session import async_session_factory, engine
from online_cinema_api.security.token_manager import JWTAuthManager

TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "Test1234!"
# bcrypt(rounds=14) hash of TEST_PASSWORD, precomputed so the fixture
# doesn't depend on a bcrypt backend being installed.
TEST_PASSWORD_HASH = "$2b$14$fBpTOLq5U4OGr845k3CgGuPG/Gdq4bksvp4EHPtEiwoiFvz3iFH6i"

MOVIES = [
    {
        "name": "The Shawshank Redemption",
        "year": 1994,
        "time": 142,
        "imdb": 9.3,
        "votes": 2_900_000,
        "meta_score": 82.0,
        "gross": 28.34,
        "description": "Two imprisoned men bond over a number of years.",
        "price": Decimal("9.99"),
        "genres": ["Drama"],
    },
    {
        "name": "The Dark Knight",
        "year": 2008,
        "time": 152,
        "imdb": 9.0,
        "votes": 2_800_000,
        "meta_score": 84.0,
        "gross": 534.86,
        "description": "Batman faces the Joker.",
        "price": Decimal("12.50"),
        "genres": ["Action", "Drama"],
    },
    {
        "name": "Inception",
        "year": 2010,
        "time": 148,
        "imdb": 8.8,
        "votes": 2_500_000,
        "meta_score": 74.0,
        "gross": 292.58,
        "description": "A thief steals secrets through dream-sharing.",
        "price": Decimal("7.00"),
        "genres": ["Action"],
    },
]


async def get_or_create(db: AsyncSession, model, defaults: dict | None = None, **lookup):
    obj = await db.scalar(select(model).filter_by(**lookup))
    if obj is None:
        obj = model(**lookup, **(defaults or {}))
        db.add(obj)
        await db.flush()
    return obj


async def seed(db: AsyncSession) -> tuple[UserModel, list[Movie], Order]:
    groups = {
        g: await get_or_create(db, UserGroupModel, name=g) for g in UserGroupEnum
    }

    user = await db.scalar(select(UserModel).where(UserModel.email == TEST_EMAIL))
    if user is None:
        user = UserModel(
            email=TEST_EMAIL,
            group_id=groups[UserGroupEnum.USER].id,
            is_active=True,
        )
        user._hashed_password = TEST_PASSWORD_HASH
        db.add(user)
        await db.flush()

    certification = await get_or_create(db, Certification, name="PG-13")
    director = await get_or_create(db, Director, name="Christopher Nolan")
    star = await get_or_create(db, Star, name="Morgan Freeman")

    movies = []
    for data in MOVIES:
        data = dict(data)
        genre_names = data.pop("genres")
        movie = await db.scalar(
            select(Movie)
            .options(
                selectinload(Movie.genres),
                selectinload(Movie.directors),
                selectinload(Movie.stars),
            )
            .filter_by(name=data["name"], year=data["year"], time=data["time"])
        )
        if movie is None:
            movie = Movie(**data, certification_id=certification.id)
            movie.genres = [
                await get_or_create(db, Genre, name=name) for name in genre_names
            ]
            movie.directors = [director]
            movie.stars = [star]
            db.add(movie)
            await db.flush()
        movies.append(movie)

    order = await db.scalar(
        select(Order).where(
            Order.user_id == user.id, Order.status == OrderStatusEnum.PENDING
        )
    )
    if order is None:
        ordered = movies[:2]
        order = Order(
            user_id=user.id,
            status=OrderStatusEnum.PENDING,
            total_amount=sum(m.price for m in ordered),
            items=[OrderItem(movie_id=m.id, price_at_order=m.price) for m in ordered],
        )
        db.add(order)
        await db.flush()

    await db.commit()
    return user, movies, order


async def main() -> None:
    async with async_session_factory() as db:
        user, movies, order = await seed(db)
    await engine.dispose()

    settings = get_settings()
    token = JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM,
    ).create_access_token({"sub": user.email, "user_id": user.id})

    print(f"User:   {user.email} / {TEST_PASSWORD} (id={user.id})")
    print("Movies: " + ", ".join(f"{m.id}={m.name} (${m.price})" for m in movies))
    print(f"Order:  id={order.id}, status=pending, total=${order.total_amount}")
    print(f"\nAccess token (valid 60 min):\n{token}")


if __name__ == "__main__":
    asyncio.run(main())
