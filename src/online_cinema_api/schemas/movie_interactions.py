from typing import Annotated

from pydantic import BaseModel, Field

from online_cinema_api.db.models.movie_interactions import ReactionType


class ReactionRequest(BaseModel):
    reaction: ReactionType


class RatingRequest(BaseModel):
    score: Annotated[int, Field(ge=1, le=10)]


class MovieStatsSchema(BaseModel):
    likes: int
    dislikes: int
    rating_avg: float | None
    ratings_count: int
