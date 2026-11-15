from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from online_cinema_api.db.models.movie_interactions import (
    Comment,
    CommentLike,
    Notification,
    NotificationType,
)
from online_cinema_api.schemas.movie_comments import CommentSchema, NotificationSchema


def _likes_count_subquery():
    return (
        select(func.count())
        .select_from(CommentLike)
        .where(CommentLike.comment_id == Comment.id)
        .correlate(Comment)
        .scalar_subquery()
    )


def _replies_count_subquery():
    reply = aliased(Comment)
    return (
        select(func.count(reply.id))
        .where(reply.parent_id == Comment.id)
        .correlate(Comment)
        .scalar_subquery()
    )


def _comments_query():
    return select(
        Comment,
        _likes_count_subquery().label("likes_count"),
        _replies_count_subquery().label("replies_count"),
    )


def _to_comment_schema(
    comment: Comment, likes_count: int, replies_count: int
) -> CommentSchema:
    return CommentSchema(
        id=comment.id,
        movie_id=comment.movie_id,
        user_id=comment.user_id,
        parent_id=comment.parent_id,
        text=comment.text,
        created_at=comment.created_at,
        likes_count=likes_count,
        replies_count=replies_count,
    )


async def get_comment(db: AsyncSession, comment_id: int) -> Comment | None:
    return await db.scalar(select(Comment).where(Comment.id == comment_id))


async def get_comment_view(db: AsyncSession, comment_id: int) -> CommentSchema | None:
    row = (
        await db.execute(_comments_query().where(Comment.id == comment_id))
    ).one_or_none()
    if row is None:
        return None
    return _to_comment_schema(*row)


async def list_comments(
    db: AsyncSession, conditions: list, offset: int, limit: int
) -> tuple[list[CommentSchema], int]:
    total = await db.scalar(select(func.count(Comment.id)).where(*conditions)) or 0
    rows = await db.execute(
        _comments_query()
        .where(*conditions)
        .order_by(Comment.created_at.desc(), Comment.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [_to_comment_schema(*row) for row in rows], total


async def delete_comment_by_id(db: AsyncSession, comment_id: int) -> None:
    await db.execute(delete(Comment).where(Comment.id == comment_id))
    await db.commit()


async def get_comment_like(
    db: AsyncSession, user_id: int, comment_id: int
) -> CommentLike | None:
    return await db.scalar(
        select(CommentLike).where(
            CommentLike.user_id == user_id, CommentLike.comment_id == comment_id
        )
    )


async def count_comment_likes(db: AsyncSession, comment_id: int) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(CommentLike)
            .where(CommentLike.comment_id == comment_id)
        )
        or 0
    )


def _to_notification_schema(
    notification: Notification, movie_id: int
) -> NotificationSchema:
    return NotificationSchema(
        id=notification.id,
        type=notification.type,
        actor_id=notification.actor_id,
        comment_id=notification.comment_id,
        movie_id=movie_id,
        is_read=notification.is_read,
        created_at=notification.created_at,
    )


async def delete_unread_like_notifications(
    db: AsyncSession, actor_id: int, comment_id: int
) -> None:
    await db.execute(
        delete(Notification).where(
            Notification.actor_id == actor_id,
            Notification.comment_id == comment_id,
            Notification.type == NotificationType.COMMENT_LIKE,
            Notification.is_read.is_(False),
        )
    )


async def list_notifications(
    db: AsyncSession, user_id: int, unread_only: bool, offset: int, limit: int
) -> tuple[list[NotificationSchema], int]:
    conditions = [Notification.user_id == user_id]
    if unread_only:
        conditions.append(Notification.is_read.is_(False))

    total = await db.scalar(select(func.count(Notification.id)).where(*conditions)) or 0
    rows = await db.execute(
        select(Notification, Comment.movie_id)
        .join(Comment, Comment.id == Notification.comment_id)
        .where(*conditions)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [_to_notification_schema(*row) for row in rows], total


async def get_notification(
    db: AsyncSession, user_id: int, notification_id: int
) -> tuple[Notification, int] | None:
    row = (
        await db.execute(
            select(Notification, Comment.movie_id)
            .join(Comment, Comment.id == Notification.comment_id)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
        )
    ).one_or_none()
    return None if row is None else (row[0], row[1])


async def mark_all_read(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await db.commit()
    return result.rowcount
