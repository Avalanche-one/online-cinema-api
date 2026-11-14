import asyncio
from decimal import Decimal

from sqlalchemy import select

from online_cinema_api.db.models.movies import (
    Certification,
    Director,
    Genre,
    Movie,
    Star,
)
from online_cinema_api.db.session import async_session_factory


async def get_or_create(session, model, name: str):
    instance = await session.scalar(
        select(model).where(model.name == name)
    )

    if instance is None:
        instance = model(name=name)
        session.add(instance)
        await session.flush()

    return instance


async def seed_database() -> None:
    async with async_session_factory() as session:
        drama = await get_or_create(session, Genre, "Drama")
        crime = await get_or_create(session, Genre, "Crime")

        director = await get_or_create(
            session, Director, "Francis Ford Coppola"
        )

        star = await get_or_create(session, Star, "Al Pacino")
        certification = await get_or_create(session, Certification, "R")

        existing_movie = await session.scalar(
            select(Movie).where(
                Movie.name == "The Godfather",
                Movie.year == 1972,
                Movie.time == 175,
            )
        )

        if existing_movie is None:
            session.add(
                Movie(
                    name="The Godfather",
                    year=1972,
                    time=175,
                    imdb=9.2,
                    votes=2000000,
                    meta_score=100,
                    gross=250_000_000,
                    description="The aging patriarch of a crime dynasty...",
                    price=Decimal("9.99"),
                    certification=certification,
                    genres=[drama, crime],
                    directors=[director],
                    stars=[star],
                )
            )

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_database())
