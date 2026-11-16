from decimal import Decimal

import pytest
from sqlalchemy import select

from online_cinema_api.db.models import CartItem, Genre, Star
from online_cinema_api.db.models.accounts import UserGroupEnum

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (None, 401),
        (UserGroupEnum.USER, 403),
        (UserGroupEnum.MODERATOR, 201),
        (UserGroupEnum.ADMIN, 201),
    ],
)
async def test_access_to_moderator_endpoints(
    client, make_user, act_as, role, expected_status
):
    if role is not None:
        act_as(await make_user(f"{role.value}@example.com", role))
    response = await client.post("/admin/genres", json={"name": "Action"})
    assert response.status_code == expected_status


async def test_named_entities_crud(client, moderator, act_as):
    act_as(moderator)
    for path in ("genres", "stars", "directors"):
        created = await client.post(f"/admin/{path}", json={"name": "First"})
        assert created.status_code == 201
        entity_id = created.json()["id"]

        duplicate = await client.post(f"/admin/{path}", json={"name": "First"})
        assert duplicate.status_code == 409

        renamed = await client.put(
            f"/admin/{path}/{entity_id}", json={"name": "Second"}
        )
        assert renamed.json()["name"] == "Second"

        listing = await client.get(f"/admin/{path}")
        assert [item["name"] for item in listing.json()] == ["Second"]

        assert (await client.delete(f"/admin/{path}/{entity_id}")).status_code == 204
        assert (await client.delete(f"/admin/{path}/{entity_id}")).status_code == 404


async def test_create_movie(client, moderator, act_as, make_entity, movie_payload):
    genre = await make_entity(Genre, "Action")
    star = await make_entity(Star, "Actor")
    act_as(moderator)

    response = await client.post(
        "/admin/movies",
        json=movie_payload(genre_ids=[genre.id], star_ids=[star.id]),
    )
    body = response.json()
    assert response.status_code == 201
    assert [g["name"] for g in body["genres"]] == ["Action"]
    assert [s["name"] for s in body["stars"]] == ["Actor"]
    assert (await client.get(f"/movies/{body['id']}")).status_code == 200


async def test_create_movie_validation_errors(client, moderator, act_as, movie_payload):
    act_as(moderator)
    assert (await client.post("/admin/movies", json=movie_payload())).status_code == 201
    assert (await client.post("/admin/movies", json=movie_payload())).status_code == 409

    cases = [
        movie_payload(name="Other", certification_id=999999),
        movie_payload(name="Other", genre_ids=[999999]),
        movie_payload(name="Other", imdb=11),
        movie_payload(name="Other", price="-1"),
    ]
    for payload in cases:
        assert (await client.post("/admin/movies", json=payload)).status_code == 422


async def test_update_movie_changes_only_sent_fields(
    client, moderator, act_as, make_entity, movie_payload
):
    genre = await make_entity(Genre, "Drama")
    act_as(moderator)
    created = (await client.post("/admin/movies", json=movie_payload())).json()

    response = await client.patch(
        f"/admin/movies/{created['id']}", json={"price": "19.50"}
    )
    body = response.json()
    assert response.status_code == 200
    assert Decimal(str(body["price"])) == Decimal("19.50")
    assert body["name"] == created["name"]
    assert body["year"] == created["year"]

    response = await client.patch(
        f"/admin/movies/{created['id']}", json={"genre_ids": [genre.id]}
    )
    assert [g["name"] for g in response.json()["genres"]] == ["Drama"]

    missing = await client.patch("/admin/movies/999999", json={"price": "1"})
    assert missing.status_code == 404


async def test_delete_movie_without_dependencies(client, moderator, act_as, make_movie):
    movie_id = (await make_movie()).id
    act_as(moderator)

    assert (await client.delete(f"/admin/movies/{movie_id}")).status_code == 204
    assert (await client.get(f"/movies/{movie_id}")).status_code == 404
    assert (await client.delete(f"/admin/movies/{movie_id}")).status_code == 404


async def test_delete_movie_in_carts_warns_and_force_removes(
    client, db, user, moderator, act_as, make_movie, add_to_cart
):
    movie = await make_movie()
    movie_id = movie.id
    await add_to_cart(user, movie)
    act_as(moderator)

    warning = await client.delete(f"/admin/movies/{movie_id}")
    assert warning.status_code == 409
    assert (await client.get(f"/movies/{movie_id}")).status_code == 200

    forced = await client.delete(f"/admin/movies/{movie_id}", params={"force": "true"})
    assert forced.status_code == 204
    assert (await client.get(f"/movies/{movie_id}")).status_code == 404
    left = await db.scalar(select(CartItem).where(CartItem.movie_id == movie_id))
    assert left is None


async def test_delete_movie_with_orders_is_forbidden_even_with_force(
    client, user, moderator, act_as, make_movie, add_to_order
):
    movie = await make_movie()
    movie_id = movie.id
    await add_to_order(user, movie)
    act_as(moderator)

    for params in ({}, {"force": "true"}):
        response = await client.delete(f"/admin/movies/{movie_id}", params=params)
        assert response.status_code == 409
        assert "orders" in response.json()["detail"]
    assert (await client.get(f"/movies/{movie_id}")).status_code == 200
