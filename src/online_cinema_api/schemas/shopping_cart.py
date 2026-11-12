from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CartItemAdd(BaseModel):
    movie_id: int


class CartMovieResponse(BaseModel):
    id: int
    name: str
    price: Decimal
    year: int
    genres: list[str]
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CartResponse(BaseModel):
    items: list[CartMovieResponse]
    total_price: Decimal


class CartItemResponse(BaseModel):
    id: int
    added_at: datetime
    movie_id: int

    model_config = ConfigDict(from_attributes=True)
