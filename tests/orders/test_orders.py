from decimal import Decimal

from fastapi.testclient import TestClient

from online_cinema_api.db.models import OrderStatusEnum


def test_create_order_success(
    client: TestClient, make_user, movies: dict[str, int], add_to_cart
):
    user = make_user("user@example.com")
    add_to_cart(user.id, [movies["one"], movies["two"]])
    response = client.post("/api/v1/orders/", headers=user.headers)

    assert response.status_code == 201
    data = response.json()

    assert Decimal(str(data["total_amount"])) == Decimal("24.49")
    assert data["status"] == OrderStatusEnum.PENDING.value
    assert len(data["items"]) == 2


def test_create_order_empty_cart(client: TestClient, make_user):
    user = make_user("empty_cart@example.com")

    response = client.post("/api/v1/orders/", headers=user.headers)

    assert response.status_code == 400
    assert "There are no movies available" in response.json()["detail"]


def test_create_order_pending_exists(
    client: TestClient, make_user, movies: dict[str, int], add_to_cart, make_order
):
    user = make_user("pending@example.com")
    make_order(user.id, [movies["one"]], status=OrderStatusEnum.PENDING)
    add_to_cart(user.id, [movies["one"]])

    response = client.post("/api/v1/orders/", headers=user.headers)
    assert response.status_code in (400, 409)


def test_order_removes_purchased_or_unavailable_movies(
    client: TestClient, make_user, movies: dict[str, int], add_to_cart, make_order
):
    user = make_user("cleanup@example.com")
    make_order(user.id, [movies["one"]], status=OrderStatusEnum.PAID)
    add_to_cart(user.id, [movies["one"], movies["two"]])
    response = client.post("/api/v1/orders/", headers=user.headers)

    assert response.status_code == 201
    data = response.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["movie_id"] == movies["two"]

    assert (
        "Removed from the cart" in data.get("detail", "")
        or "Test Movie One" in response.text
    )
