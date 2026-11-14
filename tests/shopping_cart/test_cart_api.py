import pytest

pytestmark = pytest.mark.anyio


async def test_add_movie_in_cart(auth_client, movie):
    response = await auth_client.post("/api/v1/cart/items", json={"movie_id": movie.id})

    assert response.status_code == 201
    assert response.json()["movie_id"] == movie.id


async def test_add_movie_twice_in_cart(auth_client, movie, add_movie_in_cart):
    response = await auth_client.post("/api/v1/cart/items", json={"movie_id": movie.id})

    assert response.status_code == 409


async def test_delete_movie(auth_client, movie, add_movie_in_cart):
    response = await auth_client.delete(f"/api/v1/cart/items/{movie.id}")
    assert response.status_code == 204


async def test_delete_if_movie_not_in_cart(auth_client, movie, add_movie_in_cart):
    response = await auth_client.delete(f"/api/v1/cart/items/{4}")
    assert response.status_code == 404


async def test_read_cart(auth_client, movie, add_movie_in_cart):
    response = await auth_client.get("/api/v1/cart")
    assert movie.id == response.json()["items"][0]["id"]


async def test_read_cart_not_authenticated(client, movie, add_movie_in_cart):
    response = await client.get("/api/v1/cart")
    assert response.status_code == 401


async def test_dell_all_movie_in_cart(auth_client, movie, add_movie_in_cart):
    response = await auth_client.delete("/api/v1/cart")
    assert response.status_code == 204


async def test_all_user_item_in_cart_only_admin(
    auth_client, user, movie, add_movie_in_cart
):
    response = await auth_client.get(f"/api/v1/admin/carts/{user.id}")
    print(response.json())
    print(response.status_code)
    assert movie.id == response.json()["items"][0]["id"]


async def test_get_paid_items(auth_client, movie, add_movie_in_cart, paid_order):
    response = await auth_client.get("/api/v1/cart/purchased")
    assert response.status_code == 200
    assert response.json()[0]["id"] == movie.id
