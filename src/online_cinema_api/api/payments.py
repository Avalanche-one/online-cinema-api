import os
from decimal import ROUND_HALF_UP, Decimal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.db.models import Order, OrderStatusEnum, UserModel
from online_cinema_api.db.models.payments import PaymentModel, PaymentStatus
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies import get_current_user

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/api/v1")

router = APIRouter(tags=["Payments"])


def to_cents(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@router.post("/checkout/{order_id}")
async def checkout(
    order_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    order = await db.get(Order, order_id)

    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatusEnum.PENDING:
        raise HTTPException(status_code=400, detail="Order cannot be paid")

    amount = order.total_amount
    if not amount or amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid order amount")

    payment = PaymentModel(
        user_id=current_user.id,
        order_id=order.id,
        amount=amount,
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    # TODO: create PaymentItem

    try:
        stripe_session = await stripe.checkout.Session.create_async(
            mode="payment",
            customer_email=current_user.email,
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": to_cents(amount),
                    "product_data": {"name": f"Order #{order.id}"},
                },
                "quantity": 1,
            }],
            success_url=f"{BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/cancel",
            metadata={
                "payment_id": str(payment.id),
                "order_id": str(order.id),
            },
        )
    except stripe.StripeError:
        payment.status = PaymentStatus.CANCELED
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Payment failed. Try a different payment method or try again later.",
        )

    payment.external_payment_id = stripe_session.id
    await db.commit()

    return {"url": stripe_session.url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            request.headers.get("stripe-signature"),
            WEBHOOK_SECRET,
        )
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook")

    obj = event["data"]["object"]

    if event["type"] == "checkout.session.completed":
        payment = await db.get(PaymentModel, int(obj["metadata"]["payment_id"]))

        if not payment or payment.status != PaymentStatus.PENDING:
            return {"status": "ignored"}

        if obj["payment_status"] != "paid" or obj["amount_total"] != to_cents(payment.amount):
            payment.status = PaymentStatus.CANCELED
            await db.commit()
            return {"status": "amount_mismatch"}

        payment.status = PaymentStatus.SUCCESSFUL
        payment.external_payment_id = obj["payment_intent"]  # pi_... нужен для refund

        order = await db.get(Order, payment.order_id)
        order.status = OrderStatusEnum.PAID

        await db.commit()

        # TODO: email sending

    elif event["type"] == "checkout.session.expired":
        payment = await db.get(PaymentModel, int(obj["metadata"]["payment_id"]))
        if payment and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.CANCELED
            await db.commit()

    elif event["type"] == "charge.refunded":
        result = await db.execute(
            select(PaymentModel).where(
                PaymentModel.external_payment_id == obj["payment_intent"]
            )
        )
        payment = result.scalar_one_or_none()
        if payment:
            payment.status = PaymentStatus.REFUNDED
            await db.commit()

    return {"status": "success"}


@router.get("/success")
async def success(session_id: str):
    stripe_session = await stripe.checkout.Session.retrieve_async(session_id)
    if stripe_session.payment_status == "paid":
        return {"message": "Payment completed!"}
    return {"message": "Payment is being processed."}


@router.get("/cancel")
async def cancel():
    return {
        "message": "Payment canceled.",
        "recommendation": "Try a different payment method or try again later.",
    }


# TODO: GET /payments —  history of payments for current user
# TODO: GET /payments — if user is moderator, history with filters
