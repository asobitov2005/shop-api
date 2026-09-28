from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.orders.models import Order
from app.orders.transitions import cancel_locked_order, pay_locked_order
from app.payments.models import PaymentTransaction
from app.payments.schemas import TaskCallback
from app.products.cache import ProductCache


@dataclass(frozen=True)
class CallbackResponse:
    transaction_id: str
    order_id: int
    status: str


def amount_matches_order(order: Order, amount: Decimal) -> bool:
    return order.total_amount == amount


def _response(transaction: PaymentTransaction) -> CallbackResponse:
    return CallbackResponse(
        transaction_id=transaction.external_id,
        order_id=transaction.order_id,
        status=transaction.response_status,
    )


def _same_business_request(transaction: PaymentTransaction, payload: TaskCallback) -> bool:
    return (
        transaction.order_id == payload.order_id
        and transaction.amount == payload.amount
        and transaction.request_status == payload.status
    )


def _existing_response(session: Session, payload: TaskCallback) -> CallbackResponse | None:
    try:
        transaction = session.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.provider == "simulated",
                PaymentTransaction.external_id == payload.transaction_id,
            )
        )
        if transaction is None:
            return None
        if not _same_business_request(transaction, payload):
            raise HTTPException(status_code=409, detail="Conflicting transaction")
        return _response(transaction)
    finally:
        session.rollback()


def process_task_callback(
    session: Session, payload: TaskCallback, cache: ProductCache, *, now: datetime | None = None
) -> CallbackResponse:
    replay = _existing_response(session, payload)
    if replay is not None:
        return replay

    order = session.scalar(select(Order).where(Order.id == payload.order_id).with_for_update())
    if order is None:
        session.rollback()
        raise HTTPException(status_code=404, detail="Order not found")

    existing = session.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.provider == "simulated",
            PaymentTransaction.external_id == payload.transaction_id,
        )
    )
    if existing is not None:
        if not _same_business_request(existing, payload):
            session.rollback()
            raise HTTPException(status_code=409, detail="Conflicting transaction")
        response = _response(existing)
        session.rollback()
        return response

    if not amount_matches_order(order, payload.amount):
        session.rollback()
        raise HTTPException(status_code=409, detail="Payment amount does not match order")

    current_time = now or datetime.now(UTC)
    if order.status == "pending" and order.expires_at <= current_time:
        restored = cancel_locked_order(session, order)
        session.commit()
        if restored:
            cache.invalidate()
        raise HTTPException(status_code=409, detail="Order expired")

    if payload.status == "success":
        if not pay_locked_order(order):
            session.rollback()
            raise HTTPException(status_code=409, detail="Order cannot be paid")
    elif order.status == "pending":
        cancel_locked_order(session, order)

    transaction = PaymentTransaction(
        provider="simulated",
        external_id=payload.transaction_id,
        order_id=order.id,
        amount=payload.amount,
        request_status=payload.status,
        status="processed",
        response_status=order.status,
        processed_at=current_time,
    )
    session.add(transaction)
    try:
        session.flush()
        response = _response(transaction)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        replay = _existing_response(session, payload)
        if replay is None:
            raise HTTPException(status_code=409, detail="Conflicting transaction") from error
        return replay

    if payload.status == "failed" and response.status == "cancelled":
        cache.invalidate()
    return response
