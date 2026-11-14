from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from online_cinema_api.db.models.movie_interactions import NotificationType

CommentText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class CommentCreateRequest(BaseModel):
    text: CommentText


class CommentSchema(BaseModel):
    id: int
    movie_id: int
    user_id: int
    parent_id: int | None
    text: str
    created_at: datetime
    likes_count: int
    replies_count: int


class CommentLikeResult(BaseModel):
    liked: bool
    likes_count: int


class PageParams(BaseModel):
    page: Annotated[int, Field(ge=1)] = 1
    per_page: Annotated[int, Field(ge=1, le=100)] = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class NotificationQueryParams(PageParams):
    unread_only: bool = False


class NotificationSchema(BaseModel):
    id: int
    type: NotificationType
    actor_id: int | None
    comment_id: int
    movie_id: int
    is_read: bool
    created_at: datetime


class ReadAllResult(BaseModel):
    marked: int
