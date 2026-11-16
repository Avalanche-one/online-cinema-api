import logging
import os
from datetime import UTC, datetime
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.core.exceptions import (
    InvalidPaymentAmountError,
    OrderNotFoundError,
    OrderNotPendingError,
    PaymentNotFoundError,
    PaymentNotRefundableError,
    PaymentProviderError,
)
from online_cinema_api.db.models import OrderStatusEnum, PaymentStatus
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies import (
    get_accounts_email_notificator,
    get_current_user,
)
from online_cinema_api.dependencies.accounts import required_moderator_or_admin
from online_cinema_api.exceptions import BaseEmailError
from online_cinema_api.notifications import EmailSenderInterface
from online_cinema_api.schemas import UserRead
from online_cinema_api.schemas.payments import (
    CheckoutResponseSchema,
    PaymentListResponseSchema,
    PaymentResultSchema,
    PaymentSchema,
    WebhookResponseSchema,
)
from online_cinema_api.services import orders as orders_service
from online_cinema_api.services import payments as payments_service
from online_cinema_api.services.payments import to_cents

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/api/v1")

TRY_AGAIN_RECOMMENDATION = "Try a different payment method or try again later."

router = APIRouter(prefix="/payments", tags=["Payments"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[UserRead, Depends(get_current_user)]
StaffUser = Annotated[UserRead, Depends(required_moderator_or_admin)]
EmailSender = Annotated[EmailSenderInterface, Depends(get_accounts_email_notificator)]


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


@router.post(
    "/checkout/{order_id}",
    response_model=CheckoutResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Start paying for an order",
    description=(
        "Recalculates the order total from current movie prices, creates a "
        "pending payment with an item per order line and returns a Stripe "
        "Checkout URL to redirect the user to."
    ),
    responses={
        400: {"description": "Invalid order amount or Stripe rejected the payment."},
        404: {"description": "Order not found."},
        409: {"description": "Only a pending order can be paid."},
    },
)
async def checkout(
    order_id: int, db: DbSession, current_user: CurrentUser
) -> CheckoutResponseSchema:
    order = await orders_service.get_order(db, order_id)
    if order is None or order.user_id != current_user.id:
        raise OrderNotFoundError
    if order.status != OrderStatusEnum.PENDING:
        raise OrderNotPendingError

    order = await orders_service.revalidate_order_total(db, order)
    if not order.total_amount or order.total_amount <= 0:
        raise InvalidPaymentAmountError

    payment = await payments_service.create_pending_payment(db, order, current_user.id)

    try:
        stripe_session = await stripe.checkout.Session.create_async(
            mode="payment",
            customer_email=current_user.email,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": to_cents(item.price_at_payment),
                        "product_data": {"name": item.movie_name},
                    },
                    "quantity": 1,
                }
                for item in payment.items
            ],
            success_url=f"{BASE_URL}/payments/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/payments/cancel",
            metadata={
                "payment_id": str(payment.id),
                "order_id": str(order.id),
            },
        )
    except stripe.StripeError as error:
        logger.warning("Stripe checkout failed for payment %s: %s", payment.id, error)
        await payments_service.cancel_payment(db, payment)
        raise PaymentProviderError

    await payments_service.set_external_payment_id(db, payment, stripe_session.id)
    return CheckoutResponseSchema(payment_id=payment.id, url=stripe_session.url)


@router.post(
    "/webhook",
    response_model=WebhookResponseSchema,
    summary="Stripe webhook",
    description=(
        "Receives Stripe events. Verifies the signature, then updates the "
        "payment and order status. On successful payment the purchased movies "
        "are removed from the cart and a confirmation email is sent."
    ),
    responses={400: {"description": "Invalid payload or signature."}},
)
async def stripe_webhook(
    request: Request, db: DbSession, email_sender: EmailSender
) -> WebhookResponseSchema:
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            request.headers.get("stripe-signature"),
            WEBHOOK_SECRET,
        )
    except ValueError, stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook")

    obj = event["data"]["object"]

    if event["type"] == "checkout.session.completed":
        payment = await payments_service.get_payment(
            db, int(obj["metadata"]["payment_id"])
        )
        if not payment or payment.status != PaymentStatus.PENDING:
            return WebhookResponseSchema(status="ignored")

        if obj["payment_status"] != "paid" or obj["amount_total"] != to_cents(
            payment.amount
        ):
            await payments_service.cancel_payment(db, payment)
            return WebhookResponseSchema(status="amount_mismatch")

        await payments_service.complete_payment(db, payment, obj["payment_intent"])

        payment = await payments_service.get_payment(db, payment.id)
        try:
            await email_sender.send_payment_confirmation_email(
                email=payment.user.email,
                order_id=payment.order_id,
                amount=payment.amount,
                movies=[item.movie_name for item in payment.items],
            )
        except BaseEmailError as error:
            logger.error("Payment %s confirmation email failed: %s", payment.id, error)

    elif event["type"] == "checkout.session.expired":
        payment = await payments_service.get_payment(
            db, int(obj["metadata"]["payment_id"])
        )
        if payment and payment.status == PaymentStatus.PENDING:
            await payments_service.cancel_payment(db, payment)

    elif event["type"] == "charge.refunded":
        await payments_service.mark_refunded(db, obj["payment_intent"])

    return WebhookResponseSchema(status="success")


@router.get(
    "/success",
    response_model=PaymentResultSchema,
    summary="Stripe success redirect",
)
async def success(session_id: str) -> PaymentResultSchema:
    try:
        stripe_session = await stripe.checkout.Session.retrieve_async(session_id)
    except stripe.InvalidRequestError:
        raise HTTPException(status_code=400, detail="Unknown payment session")
    if stripe_session.payment_status == "paid":
        return PaymentResultSchema(
            message="Payment completed! A confirmation was sent to your email."
        )
    return PaymentResultSchema(message="Payment is being processed.")


@router.get(
    "/cancel",
    response_model=PaymentResultSchema,
    summary="Stripe cancel redirect",
)
async def cancel() -> PaymentResultSchema:
    return PaymentResultSchema(
        message="Payment canceled.", recommendation=TRY_AGAIN_RECOMMENDATION
    )


@router.post(
    "/{payment_id}/refund",
    response_model=PaymentResultSchema,
    summary="Request a refund",
    description=(
        "Requests a full refund of a successful payment from Stripe. "
        "The payment becomes refunded and its order canceled once Stripe "
        "confirms the refund via the webhook."
    ),
    responses={
        400: {"description": "Stripe rejected the refund."},
        404: {"description": "Payment not found."},
        409: {"description": "Only a successful payment can be refunded."},
    },
)
async def refund(
    payment_id: int, db: DbSession, current_user: CurrentUser
) -> PaymentResultSchema:
    payment = await payments_service.get_payment(db, payment_id)
    if payment is None or payment.user_id != current_user.id:
        raise PaymentNotFoundError
    if payment.status != PaymentStatus.SUCCESSFUL:
        raise PaymentNotRefundableError

    try:
        await stripe.Refund.create_async(payment_intent=payment.external_payment_id)
    except stripe.StripeError as error:
        logger.warning("Stripe refund failed for payment %s: %s", payment.id, error)
        raise PaymentProviderError("Refund failed. Please try again later.")

    return PaymentResultSchema(
        message="Refund requested. The money will be returned to your card."
    )


@router.get(
    "",
    response_model=PaymentListResponseSchema,
    summary="List my payments",
    description="Returns the user's payments, newest first, with pagination.",
)
async def list_my_payments(
    db: DbSession,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    per_page: Annotated[int, Query(ge=1, le=20, description="Items per page")] = 10,
) -> PaymentListResponseSchema:
    payments, total_items, total_pages = await payments_service.list_payments(
        db, page=page, per_page=per_page, user_id=current_user.id
    )
    return PaymentListResponseSchema(
        payments=[PaymentSchema.model_validate(p) for p in payments],
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_items=total_items,
    )


@router.get(
    "/all",
    response_model=PaymentListResponseSchema,
    summary="List all payments (moderator or admin)",
    description=(
        "Returns payments of all users, newest first. "
        "Can be filtered by user, status and creation date range."
    ),
    responses={403: {"description": "Only moderators and admins can do this."}},
)
async def list_all_payments(
    db: DbSession,
    staff: StaffUser,
    user_id: Annotated[int | None, Query(description="Filter by user id")] = None,
    payment_status: Annotated[
        PaymentStatus | None, Query(alias="status", description="Filter by status")
    ] = None,
    date_from: Annotated[
        datetime | None, Query(description="Created at or after this date-time")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Created at or before this date-time")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    per_page: Annotated[int, Query(ge=1, le=20, description="Items per page")] = 10,
) -> PaymentListResponseSchema:
    payments, total_items, total_pages = await payments_service.list_payments(
        db,
        page=page,
        per_page=per_page,
        user_id=user_id,
        status=payment_status,
        date_from=_as_utc(date_from),
        date_to=_as_utc(date_to),
    )
    return PaymentListResponseSchema(
        payments=[PaymentSchema.model_validate(p) for p in payments],
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_items=total_items,
    )
