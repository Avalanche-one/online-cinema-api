from datetime import datetime

from pydantic import BaseModel, ConfigDict # noqa


class CartItemAdd(BaseModel):
    movie_id: int


class CartItemResponse(BaseModel):
    id: int
    added_at: datetime
    movie_id: int

    model_config = ConfigDict(from_attributes=True)
