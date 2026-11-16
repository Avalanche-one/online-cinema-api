from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio


async def test_actions_require_authentication(client, make_movie):
    movie = await make_movie()
    reaction = await client.post(
        f"/movies/{movie.id}/reaction", json={"reaction": "like"}
    )
    rating = await client.put(f"/movies/{movie.id}/rating", json={"score": 5})
    assert reaction.status_code == 401
    assert rating.status_code == 401
    assert (await client.post(f"/favorites/{movie.id}")).status_code == 401
    assert (await client.get("/favorites")).status_code == 401


async def test_stats_are_public_and_404_for_missing(client, make_movie):
    movie = await make_movie()
    response = await client.get(f"/movies/{movie.id}/stats")
    assert response.status_code == 200
    assert response.json() == {
        "likes": 0,
        "dislikes": 0,
        "rating_avg": None,
        "ratings_count": 0,
    }
    assert (await client.get("/movies/999999/stats")).status_code == 404


async def test_reaction_toggle_and_replace(client, user, act_as, make_movie):
    movie = await make_movie()
    act_as(user)
    url = f"/movies/{movie.id}/reaction"

    body = (await client.post(url, json={"reaction": "like"})).json()
    assert (body["likes"], body["dislikes"]) == (1, 0)

    body = (await client.post(url, json={"reaction": "like"})).json()
    assert (body["likes"], body["dislikes"]) == (0, 0)

    await client.post(url, json={"reaction": "like"})
    body = (await client.post(url, json={"reaction": "dislike"})).json()
    assert (body["likes"], body["dislikes"]) == (0, 1)


async def test_reaction_validation(client, user, act_as, make_movie):
    movie = await make_movie()
    act_as(user)
    bad = await client.post(f"/movies/{movie.id}/reaction", json={"reaction": "love"})
    missing = await client.post("/movies/999999/reaction", json={"reaction": "like"})
    assert bad.status_code == 422
    assert missing.status_code == 404


async def test_rating_upsert_average_and_delete(
    client, user, other_user, act_as, make_movie
):
    movie = await make_movie()
    url = f"/movies/{movie.id}/rating"

    act_as(user)
    body = (await client.put(url, json={"score": 8})).json()
    assert (body["rating_avg"], body["ratings_count"]) == (8.0, 1)

    body = (await client.put(url, json={"score": 10})).json()
    assert (body["rating_avg"], body["ratings_count"]) == (10.0, 1)

    act_as(other_user)
    body = (await client.put(url, json={"score": 6})).json()
    assert (body["rating_avg"], body["ratings_count"]) == (8.0, 2)

    body = (await client.delete(url)).json()
    assert (body["rating_avg"], body["ratings_count"]) == (10.0, 1)


async def test_rating_validation(client, user, act_as, make_movie):
    movie = await make_movie()
    act_as(user)
    for score in (0, 11):
        response = await client.put(f"/movies/{movie.id}/rating", json={"score": score})
        assert response.status_code == 422
    missing = await client.put("/movies/999999/rating", json={"score": 5})
    assert missing.status_code == 404


async def test_favorites_add_list_remove(client, user, act_as, make_movie):
    movie_id = (await make_movie()).id
    act_as(user)

    assert (await client.post(f"/favorites/{movie_id}")).status_code == 201
    assert (await client.post(f"/favorites/{movie_id}")).status_code == 409
    assert (await client.post("/favorites/999999")).status_code == 404

    listing = (await client.get("/favorites")).json()
    assert [item["id"] for item in listing["items"]] == [movie_id]

    assert (await client.delete(f"/favorites/{movie_id}")).status_code == 204
    assert (await client.delete(f"/favorites/{movie_id}")).status_code == 404
    assert (await client.get("/favorites")).json()["total"] == 0


async def test_favorites_support_search_filters_and_sorting(
    client, user, act_as, make_movie
):
    alpha_id = (await make_movie(name="Alpha", price=Decimal("5.00"), year=2020)).id
    beta_id = (await make_movie(name="Beta", price=Decimal("1.00"), year=2010)).id
    await make_movie(name="Gamma")
    act_as(user)
    for movie_id in (alpha_id, beta_id):
        await client.post(f"/favorites/{movie_id}")

    async def names(**params):
        response = await client.get("/favorites", params=params)
        return [item["name"] for item in response.json()["items"]]

    assert await names(sort_by="price", order="asc") == ["Beta", "Alpha"]
    assert await names(search="alp") == ["Alpha"]
    assert await names(year_from=2015) == ["Alpha"]
    assert await names(per_page=1, page=2, sort_by="price", order="asc") == ["Alpha"]


async def test_favorites_are_private_per_user(
    client, user, other_user, act_as, make_movie
):
    movie_id = (await make_movie()).id
    act_as(user)
    await client.post(f"/favorites/{movie_id}")

    act_as(other_user)
    assert (await client.get("/favorites")).json()["total"] == 0
    assert (await client.delete(f"/favorites/{movie_id}")).status_code == 404
