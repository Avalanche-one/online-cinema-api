from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from online_cinema_api.db.models import OrderStatusEnum


class OrderItemSchema(BaseModel):
    id: int
    movie_id: int
    price_at_order: Decimal

    model_config = ConfigDict(from_attributes=True)


class OrderSchema(BaseModel):
    id: int
    user_id: int
    created_at: datetime
    status: OrderStatusEnum
    total_amount: Decimal | None
    items: list[OrderItemSchema]

    model_config = ConfigDict(from_attributes=True)


class OrderListResponseSchema(BaseModel):
    orders: list[OrderSchema]
    page: int
    per_page: int
    total_pages: int
    total_items: int
