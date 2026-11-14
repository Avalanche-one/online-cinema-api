from math import ceil

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.core.movie_exceptions import (
    CommentForbiddenError,
    CommentNotFoundError,
    NotificationNotFoundError,
)
from online_cinema_api.db.models.movie_interactions import (
    Comment,
    CommentLike,
    Notification,
    NotificationType,
)
from online_cinema_api.schemas.movie_comments import (
    CommentLikeResult,
    CommentSchema,
    NotificationQueryParams,
    NotificationSchema,
    PageParams,
    ReadAllResult,
)
from online_cinema_api.schemas.movies import PaginatedResponse
from online_cinema_api.services import movie_comments as crud
from online_cinema_api.services.movie_engagement import ensure_movie_exists


async def _get_comment_or_404(db: AsyncSession, comment_id: int) -> Comment:
    comment = await crud.get_comment(db, comment_id)
    if comment is None:
        raise CommentNotFoundError
    return comment


async def _create_comment(
    db: AsyncSession,
    user_id: int,
    movie_id: int,
    text: str,
    parent: Comment | None,
) -> CommentSchema:
    comment = Comment(
        user_id=user_id,
        movie_id=movie_id,
        parent_id=parent.id if parent is not None else None,
        text=text,
    )
    db.add(comment)
    await db.flush()
    comment_id = comment.id

    if parent is not None and parent.user_id != user_id:
        db.add(
            Notification(
                user_id=parent.user_id,
                actor_id=user_id,
                comment_id=comment_id,
                type=NotificationType.COMMENT_REPLY,
            )
        )

    await db.commit()
    view = await crud.get_comment_view(db, comment_id)
    assert view is not None
    return view


async def add_comment(
    db: AsyncSession, user_id: int, movie_id: int, text: str
) -> CommentSchema:
    await ensure_movie_exists(db, movie_id)
    return await _create_comment(db, user_id, movie_id, text, parent=None)


async def add_reply(
    db: AsyncSession, user_id: int, comment_id: int, text: str
) -> CommentSchema:
    parent = await _get_comment_or_404(db, comment_id)
    return await _create_comment(db, user_id, parent.movie_id, text, parent=parent)


async def list_movie_comments(
    db: AsyncSession, movie_id: int, params: PageParams
) -> PaginatedResponse[CommentSchema]:
    await ensure_movie_exists(db, movie_id)
    items, total = await crud.list_comments(
        db,
        [Comment.movie_id == movie_id, Comment.parent_id.is_(None)],
        params.offset,
        params.per_page,
    )
    return PaginatedResponse[CommentSchema](
        items=items,
        total=total,
        page=params.page,
        per_page=params.per_page,
        pages=ceil(total / params.per_page),
    )


async def list_replies(
    db: AsyncSession, comment_id: int, params: PageParams
) -> PaginatedResponse[CommentSchema]:
    await _get_comment_or_404(db, comment_id)
    items, total = await crud.list_comments(
        db, [Comment.parent_id == comment_id], params.offset, params.per_page
    )
    return PaginatedResponse[CommentSchema](
        items=items,
        total=total,
        page=params.page,
        per_page=params.per_page,
        pages=ceil(total / params.per_page),
    )


async def delete_comment(db: AsyncSession, user_id: int, comment_id: int) -> None:
    comment = await _get_comment_or_404(db, comment_id)
    if comment.user_id != user_id:
        raise CommentForbiddenError
    await crud.delete_comment_by_id(db, comment_id)


async def toggle_comment_like(
    db: AsyncSession, user_id: int, comment_id: int
) -> CommentLikeResult:
    comment = await _get_comment_or_404(db, comment_id)

    existing = await crud.get_comment_like(db, user_id, comment_id)
    if existing is None:
        db.add(CommentLike(user_id=user_id, comment_id=comment_id))
        if comment.user_id != user_id:
            db.add(
                Notification(
                    user_id=comment.user_id,
                    actor_id=user_id,
                    comment_id=comment_id,
                    type=NotificationType.COMMENT_LIKE,
                )
            )
    else:
        await db.delete(existing)
        await crud.delete_unread_like_notifications(db, user_id, comment_id)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()

    liked = await crud.get_comment_like(db, user_id, comment_id) is not None
    return CommentLikeResult(
        liked=liked, likes_count=await crud.count_comment_likes(db, comment_id)
    )


async def list_notifications(
    db: AsyncSession, user_id: int, params: NotificationQueryParams
) -> PaginatedResponse[NotificationSchema]:
    items, total = await crud.list_notifications(
        db, user_id, params.unread_only, params.offset, params.per_page
    )
    return PaginatedResponse[NotificationSchema](
        items=items,
        total=total,
        page=params.page,
        per_page=params.per_page,
        pages=ceil(total / params.per_page),
    )


async def mark_notification_read(
    db: AsyncSession, user_id: int, notification_id: int
) -> NotificationSchema:
    row = await crud.get_notification(db, user_id, notification_id)
    if row is None:
        raise NotificationNotFoundError

    notification, _ = row
    if not notification.is_read:
        notification.is_read = True
        await db.commit()

    row = await crud.get_notification(db, user_id, notification_id)
    assert row is not None
    return crud._to_notification_schema(*row)


async def mark_all_notifications_read(db: AsyncSession, user_id: int) -> ReadAllResult:
    return ReadAllResult(marked=await crud.mark_all_read(db, user_id))
