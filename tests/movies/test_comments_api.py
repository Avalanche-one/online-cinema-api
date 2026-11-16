import pytest

pytestmark = pytest.mark.asyncio


async def _comment(client, movie_id: int, text: str = "Nice movie") -> dict:
    response = await client.post(f"/movies/{movie_id}/comments", json={"text": text})
    assert response.status_code == 201
    return response.json()


async def _notifications(client, **params) -> dict:
    response = await client.get("/notifications", params=params)
    assert response.status_code == 200
    return response.json()


async def test_create_comment(client, user, act_as, make_movie):
    movie = await make_movie()
    act_as(user)
    body = await _comment(client, movie.id, "  Great  ")
    assert body["text"] == "Great"
    assert body["user_id"] == user.id
    assert body["parent_id"] is None
    assert (body["likes_count"], body["replies_count"]) == (0, 0)


async def test_comment_validation_and_auth(client, user, act_as, make_movie):
    movie = await make_movie()
    anonymous = await client.post(f"/movies/{movie.id}/comments", json={"text": "x"})
    assert anonymous.status_code == 401

    act_as(user)
    for text in ("", "   "):
        response = await client.post(
            f"/movies/{movie.id}/comments", json={"text": text}
        )
        assert response.status_code == 422
    missing = await client.post("/movies/999999/comments", json={"text": "x"})
    assert missing.status_code == 404
    assert (await client.get("/movies/999999/comments")).status_code == 404


async def test_list_top_level_comments_and_replies(
    client, user, other_user, act_as, make_movie
):
    movie = await make_movie()
    act_as(user)
    top = await _comment(client, movie.id, "Top")
    act_as(other_user)
    reply = (
        await client.post(f"/comments/{top['id']}/replies", json={"text": "Reply"})
    ).json()
    assert reply["parent_id"] == top["id"]
    assert reply["movie_id"] == movie.id

    listing = (await client.get(f"/movies/{movie.id}/comments")).json()
    assert [c["id"] for c in listing["items"]] == [top["id"]]  # лише верхній рівень
    assert listing["items"][0]["replies_count"] == 1

    replies = (await client.get(f"/comments/{top['id']}/replies")).json()
    assert [c["id"] for c in replies["items"]] == [reply["id"]]
    assert (await client.get("/comments/999999/replies")).status_code == 404


async def test_reply_creates_notification_for_author(
    client, user, other_user, act_as, make_movie
):
    movie = await make_movie()
    act_as(user)
    top = await _comment(client, movie.id)
    act_as(other_user)
    reply = (
        await client.post(f"/comments/{top['id']}/replies", json={"text": "Reply"})
    ).json()

    act_as(user)
    notifications = await _notifications(client)
    assert notifications["total"] == 1
    item = notifications["items"][0]
    assert item["type"] == "comment_reply"
    assert item["actor_id"] == other_user.id
    assert item["comment_id"] == reply["id"]
    assert item["movie_id"] == movie.id
    assert item["is_read"] is False

    act_as(other_user)
    assert (await _notifications(client))["total"] == 0


async def test_no_notifications_for_own_actions(client, user, act_as, make_movie):
    movie = await make_movie()
    act_as(user)
    top = await _comment(client, movie.id)
    await client.post(f"/comments/{top['id']}/replies", json={"text": "Self reply"})
    await client.post(f"/comments/{top['id']}/like")
    assert (await _notifications(client))["total"] == 0


async def test_comment_like_toggle_and_notification(
    client, user, other_user, act_as, make_movie
):
    movie = await make_movie()
    act_as(user)
    top = await _comment(client, movie.id)

    act_as(other_user)
    body = (await client.post(f"/comments/{top['id']}/like")).json()
    assert body == {"liked": True, "likes_count": 1}

    act_as(user)
    items = (await _notifications(client))["items"]
    assert [n["type"] for n in items] == ["comment_like"]
    assert items[0]["comment_id"] == top["id"]

    act_as(other_user)
    body = (await client.post(f"/comments/{top['id']}/like")).json()
    assert body == {"liked": False, "likes_count": 0}

    act_as(user)
    assert (await _notifications(client))["total"] == 0
    assert (await client.post("/comments/999999/like")).status_code == 404


async def test_read_notification_survives_unlike(
    client, user, other_user, act_as, make_movie
):
    movie = await make_movie()
    act_as(user)
    top = await _comment(client, movie.id)
    act_as(other_user)
    await client.post(f"/comments/{top['id']}/like")

    act_as(user)
    notification = (await _notifications(client))["items"][0]
    await client.patch(f"/notifications/{notification['id']}/read")

    act_as(other_user)
    await client.post(f"/comments/{top['id']}/like")

    act_as(user)
    assert (await _notifications(client))["total"] == 1


async def test_mark_notifications_as_read(client, user, other_user, act_as, make_movie):
    movie = await make_movie()
    act_as(user)
    top = await _comment(client, movie.id)
    act_as(other_user)
    await client.post(f"/comments/{top['id']}/replies", json={"text": "Reply"})
    await client.post(f"/comments/{top['id']}/like")

    act_as(user)
    assert (await _notifications(client, unread_only=True))["total"] == 2
    first = (await _notifications(client))["items"][0]

    response = await client.patch(f"/notifications/{first['id']}/read")
    assert response.status_code == 200
    assert response.json()["is_read"] is True
    assert (await _notifications(client, unread_only=True))["total"] == 1

    assert (await client.post("/notifications/read-all")).json() == {"marked": 1}
    assert (await _notifications(client, unread_only=True))["total"] == 0
    assert (await _notifications(client))["total"] == 2

    act_as(other_user)
    foreign = await client.patch(f"/notifications/{first['id']}/read")
    assert foreign.status_code == 404


async def test_delete_comment_permissions_and_cascade(
    client, user, other_user, act_as, make_movie
):
    movie = await make_movie()
    act_as(user)
    top = await _comment(client, movie.id)
    act_as(other_user)
    reply = (
        await client.post(f"/comments/{top['id']}/replies", json={"text": "Reply"})
    ).json()

    assert (await client.delete(f"/comments/{top['id']}")).status_code == 403

    act_as(user)
    assert (await client.delete(f"/comments/{top['id']}")).status_code == 204
    assert (await client.delete(f"/comments/{top['id']}")).status_code == 404
    assert (await client.get(f"/comments/{reply['id']}/replies")).status_code == 404
    assert (await client.get(f"/movies/{movie.id}/comments")).json()["total"] == 0
    assert (await _notifications(client))["total"] == 0
