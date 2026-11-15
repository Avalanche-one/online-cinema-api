from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from online_cinema_api.db.models import PaymentStatus


class PaymentItemSchema(BaseModel):
    id: int
    order_item_id: int
    movie_id: int
    movie_name: str
    price_at_payment: Decimal

    model_config = ConfigDict(from_attributes=True)


class PaymentSchema(BaseModel):
    id: int
    user_id: int
    order_id: int
    created_at: datetime
    status: PaymentStatus
    amount: Decimal
    external_payment_id: str | None
    items: list[PaymentItemSchema]

    model_config = ConfigDict(from_attributes=True)


class PaymentListResponseSchema(BaseModel):
    payments: list[PaymentSchema]
    page: int
    per_page: int
    total_pages: int
    total_items: int


class CheckoutResponseSchema(BaseModel):
    payment_id: int = Field(description="ID of the created pending payment")
    url: str = Field(description="Stripe Checkout page to redirect the user to")


class PaymentResultSchema(BaseModel):
    message: str
    recommendation: str | None = None


class WebhookResponseSchema(BaseModel):
    status: str
