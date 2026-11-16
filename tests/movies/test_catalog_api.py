from decimal import Decimal

import pytest

from online_cinema_api.db.models import Director, Genre, Star

pytestmark = pytest.mark.asyncio


async def test_empty_catalog(client):
    response = await client.get("/movies")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "per_page": 20,
        "pages": 0,
    }


async def test_pagination(client, make_movie):
    movies = [await make_movie() for _ in range(5)]
    seen = []
    for page, expected in [(1, 2), (2, 2), (3, 1)]:
        response = await client.get("/movies", params={"page": page, "per_page": 2})
        body = response.json()
        assert len(body["items"]) == expected
        assert (body["total"], body["pages"]) == (5, 3)
        seen += [item["id"] for item in body["items"]]
    assert sorted(seen) == sorted(movie.id for movie in movies)


async def test_sorting(client, make_movie):
    await make_movie(name="B", price=Decimal("5.00"), year=2010, votes=1)
    await make_movie(name="A", price=Decimal("9.00"), year=2020, votes=3)
    await make_movie(name="C", price=Decimal("1.00"), year=2000, votes=2)

    async def names(**params):
        response = await client.get("/movies", params=params)
        return [item["name"] for item in response.json()["items"]]

    assert await names(sort_by="price", order="asc") == ["C", "B", "A"]
    assert await names(sort_by="price", order="desc") == ["A", "B", "C"]
    assert await names(sort_by="year", order="asc") == ["C", "B", "A"]
    assert await names(sort_by="name", order="asc") == ["A", "B", "C"]
    assert await names(sort_by="popularity") == ["A", "C", "B"]  # за votes, спадання


async def test_search_by_title_description_star_and_director(
    client, make_movie, make_entity
):
    star = await make_entity(Star, "Keanu Reeves")
    director = await make_entity(Director, "Lana Wachowski")
    await make_movie(name="The Matrix", stars=[star], directors=[director])
    await make_movie(name="Other", description="about a hidden dragon")
    await make_movie(name="Unrelated")

    async def total(search: str) -> int:
        response = await client.get("/movies", params={"search": search})
        return response.json()["total"]

    assert await total("matrix") == 1
    assert await total("dragon") == 1
    assert await total("keanu") == 1
    assert await total("wachowski") == 1
    assert await total("nothing-matches") == 0


async def test_search_treats_percent_literally(client, make_movie):
    await make_movie(name="100% Real")
    await make_movie(name="Other")
    response = await client.get("/movies", params={"search": "%"})
    assert [item["name"] for item in response.json()["items"]] == ["100% Real"]


async def test_filters(client, make_movie, make_entity, certification):
    genre = await make_entity(Genre, "Drama")
    star = await make_entity(Star, "Some Star")
    director = await make_entity(Director, "Some Director")
    await make_movie(
        name="Target",
        year=2015,
        imdb=8.5,
        price=Decimal("4.00"),
        genres=[genre],
        stars=[star],
        directors=[director],
    )
    await make_movie(name="Old", year=1990, imdb=4.0, price=Decimal("20.00"))

    async def names(**params):
        response = await client.get("/movies", params=params)
        return [item["name"] for item in response.json()["items"]]

    assert await names(year_from=2000) == ["Target"]
    assert await names(year_to=2000) == ["Old"]
    assert await names(imdb_min=8) == ["Target"]
    assert await names(imdb_max=5) == ["Old"]
    assert await names(price_max=5) == ["Target"]
    assert await names(price_min=10) == ["Old"]
    assert await names(genre_id=genre.id) == ["Target"]
    assert await names(star_id=star.id) == ["Target"]
    assert await names(director_id=director.id) == ["Target"]
    assert len(await names(certification_id=certification.id)) == 2
    assert await names(year_from=2000, imdb_min=9) == []


async def test_invalid_ranges_return_422(client):
    response = await client.get("/movies", params={"year_from": 2020, "year_to": 2010})
    assert response.status_code == 422


async def test_movie_details(client, make_movie, make_entity):
    genre = await make_entity(Genre, "Action")
    star = await make_entity(Star, "Actor")
    director = await make_entity(Director, "Director")
    movie = await make_movie(genres=[genre], stars=[star], directors=[director])

    response = await client.get(f"/movies/{movie.id}")
    body = response.json()
    assert response.status_code == 200
    assert body["id"] == movie.id
    assert [g["name"] for g in body["genres"]] == ["Action"]
    assert [s["name"] for s in body["stars"]] == ["Actor"]
    assert [d["name"] for d in body["directors"]] == ["Director"]
    assert body["certification"]["name"]


async def test_movie_details_not_found_and_invalid_id(client):
    assert (await client.get("/movies/999999")).status_code == 404
    assert (await client.get("/movies/0")).status_code == 422


async def test_genres_with_movie_counts(client, make_movie, make_entity):
    action = await make_entity(Genre, "Action")
    await make_entity(Genre, "Western")
    await make_movie(genres=[action])
    await make_movie(genres=[action])

    response = await client.get("/genres")
    result = {item["name"]: item["movies_count"] for item in response.json()}
    assert result == {"Action": 2, "Western": 0}
