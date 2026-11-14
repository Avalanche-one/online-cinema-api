from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies.accounts import get_current_user
from online_cinema_api.schemas import UserRead
from online_cinema_api.schemas.movie_comments import (
    CommentCreateRequest,
    CommentLikeResult,
    CommentSchema,
    NotificationQueryParams,
    NotificationSchema,
    PageParams,
    ReadAllResult,
)
from online_cinema_api.schemas.movies import PaginatedResponse
from online_cinema_api.services import comment_engagement

router = APIRouter()

Id = Annotated[int, Path(ge=1)]


@router.get(
    "/movies/{movie_id}/comments",
    response_model=PaginatedResponse[CommentSchema],
    tags=["comments"],
    summary="List top-level comments of a movie (newest first)",
    description="Replies are loaded separately via GET /comments/{comment_id}/replies.",
    responses={404: {"description": "Movie not found"}},
)
async def list_comments(
    movie_id: Id,
    params: Annotated[PageParams, Query()],
    db: AsyncSession = Depends(get_db_session),
):
    return await comment_engagement.list_movie_comments(db, movie_id, params)


@router.post(
    "/movies/{movie_id}/comments",
    response_model=CommentSchema,
    status_code=status.HTTP_201_CREATED,
    tags=["comments"],
    summary="Write a comment on a movie",
    responses={404: {"description": "Movie not found"}},
)
async def create_comment(
    movie_id: Id,
    data: CommentCreateRequest,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await comment_engagement.add_comment(
        db, current_user.id, movie_id, data.text
    )


@router.get(
    "/comments/{comment_id}/replies",
    response_model=PaginatedResponse[CommentSchema],
    tags=["comments"],
    summary="List replies to a comment (newest first)",
    responses={404: {"description": "Comment not found"}},
)
async def list_replies(
    comment_id: Id,
    params: Annotated[PageParams, Query()],
    db: AsyncSession = Depends(get_db_session),
):
    return await comment_engagement.list_replies(db, comment_id, params)


@router.post(
    "/comments/{comment_id}/replies",
    response_model=CommentSchema,
    status_code=status.HTTP_201_CREATED,
    tags=["comments"],
    summary="Reply to a comment",
    description="The author of the comment is notified (unless they reply to themselves).",
    responses={404: {"description": "Comment not found"}},
)
async def reply_to_comment(
    comment_id: Id,
    data: CommentCreateRequest,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await comment_engagement.add_reply(
        db, current_user.id, comment_id, data.text
    )


@router.post(
    "/comments/{comment_id}/like",
    response_model=CommentLikeResult,
    tags=["comments"],
    summary="Like a comment (calling again removes the like)",
    description="The author of the comment is notified (unless they like their own comment).",
    responses={404: {"description": "Comment not found"}},
)
async def like_comment(
    comment_id: Id,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await comment_engagement.toggle_comment_like(db, current_user.id, comment_id)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["comments"],
    summary="Delete your own comment (its replies and likes are deleted too)",
    responses={
        403: {"description": "Not your comment"},
        404: {"description": "Comment not found"},
    },
)
async def delete_comment(
    comment_id: Id,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await comment_engagement.delete_comment(db, current_user.id, comment_id)


@router.get(
    "/notifications",
    response_model=PaginatedResponse[NotificationSchema],
    tags=["notifications"],
    summary="List your notifications about replies and likes (newest first)",
)
async def list_notifications(
    params: Annotated[NotificationQueryParams, Query()],
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await comment_engagement.list_notifications(db, current_user.id, params)


@router.post(
    "/notifications/read-all",
    response_model=ReadAllResult,
    tags=["notifications"],
    summary="Mark all your notifications as read",
)
async def read_all_notifications(
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await comment_engagement.mark_all_notifications_read(db, current_user.id)


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationSchema,
    tags=["notifications"],
    summary="Mark a notification as read",
    responses={404: {"description": "Notification not found"}},
)
async def read_notification(
    notification_id: Id,
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return await comment_engagement.mark_notification_read(
        db, current_user.id, notification_id
    )
