import pytest

from online_cinema_api.db.models.accounts import UserGroupEnum

pytestmark = pytest.mark.asyncio


async def test_catalog_to_notifications_journey(
    client, make_user, act_as, certification
):
    moderator = await make_user("mod@example.com", UserGroupEnum.MODERATOR)
    alice = await make_user("alice@example.com")
    bob = await make_user("bob@example.com")

    act_as(moderator)
    genre = (await client.post("/admin/genres", json={"name": "Sci-Fi"})).json()
    star = (await client.post("/admin/stars", json={"name": "Jane Actor"})).json()
    director = (
        await client.post("/admin/directors", json={"name": "Joe Director"})
    ).json()

    movie_ids = {}
    for name, year, imdb, price in [
        ("Alpha Quest", 2015, 8.5, "4.99"),
        ("Beta Run", 2021, 6.0, "9.99"),
        ("Gamma Ray", 2023, 7.2, "14.99"),
    ]:
        response = await client.post(
            "/admin/movies",
            json={
                "name": name,
                "year": year,
                "time": 100,
                "imdb": imdb,
                "votes": 1000,
                "description": f"{name} description",
                "price": price,
                "certification_id": certification.id,
                "genre_ids": [genre["id"]],
                "star_ids": [star["id"]],
                "director_ids": [director["id"]],
            },
        )
        assert response.status_code == 201
        movie_ids[name] = response.json()["id"]

    act_as(alice)
    response = await client.get(
        "/movies",
        params={
            "genre_id": genre["id"],
            "imdb_min": 7,
            "sort_by": "price",
            "order": "desc",
        },
    )
    assert [m["name"] for m in response.json()["items"]] == ["Gamma Ray", "Alpha Quest"]
    assert (await client.get("/movies", params={"search": "Jane"})).json()["total"] == 3

    genres = (await client.get("/genres")).json()
    assert [(g["name"], g["movies_count"]) for g in genres] == [("Sci-Fi", 3)]

    alpha = movie_ids["Alpha Quest"]
    assert (await client.post(f"/favorites/{alpha}")).status_code == 201
    assert (await client.get("/favorites")).json()["total"] == 1
    old_only = await client.get("/favorites", params={"year_from": 2020})
    assert old_only.json()["total"] == 0

    stats = (
        await client.post(f"/movies/{alpha}/reaction", json={"reaction": "like"})
    ).json()
    assert stats["likes"] == 1
    stats = (await client.put(f"/movies/{alpha}/rating", json={"score": 9})).json()
    assert (stats["rating_avg"], stats["ratings_count"]) == (9.0, 1)

    comment = (
        await client.post(f"/movies/{alpha}/comments", json={"text": "Great movie"})
    ).json()
    act_as(bob)
    reply = await client.post(
        f"/comments/{comment['id']}/replies", json={"text": "Agreed"}
    )
    assert reply.status_code == 201
    like = (await client.post(f"/comments/{comment['id']}/like")).json()
    assert like["likes_count"] == 1

    act_as(alice)
    unread = (await client.get("/notifications", params={"unread_only": True})).json()
    assert unread["total"] == 2
    assert {n["type"] for n in unread["items"]} == {"comment_reply", "comment_like"}
    assert (await client.post("/notifications/read-all")).json() == {"marked": 2}
    unread = (await client.get("/notifications", params={"unread_only": True})).json()
    assert unread["total"] == 0

    listing = (await client.get(f"/movies/{alpha}/comments")).json()
    assert listing["items"][0]["likes_count"] == 1
    assert listing["items"][0]["replies_count"] == 1
