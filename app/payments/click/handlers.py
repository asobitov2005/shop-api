import secrets
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.orders.models import Order
from app.orders.transitions import cancel_locked_order, pay_locked_order
from app.payments.click.schemas import (
    CompleteFields,
    CompleteResponse,
    PrepareFields,
    PrepareResponse,
)
from app.payments.click.signatures import complete_signature, prepare_signature
from app.payments.models import PaymentTransaction
from app.payments.service import amount_matches_order
from app.products.cache import ProductCache

ResultCode = tuple[int, str]
Result = tuple[ResultCode, int, str, int]

SIGNATURE_ERROR = (-1, "SIGN CHECK FAILED")
AMOUNT_ERROR = (-2, "Incorrect parameter amount")
ACTION_ERROR = (-3, "Incorrect action")
PAID_ERROR = (-4, "Transaction already confirmed")
ORDER_ERROR = (-5, "Order does not exist")
PREPARE_ERROR = (-6, "Prepare transaction does not exist")
CANCELLED_ERROR = (-9, "Transaction cancelled")


def _positive_int(value: str) -> int | None:
    if len(value) > 19 or not value.isdecimal():
        return None
    try:
        result = int(value)
    except ValueError:
        return None
    if result > 9_223_372_036_854_775_807:
        return None
    return result if result > 0 else None


def _amount(value: str) -> Decimal | None:
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount > 0 else None


def _signed_int(value: str) -> int | None:
    if len(value) > 11 or not value.lstrip("-").isdecimal():
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _error(code: ResultCode, click_id: int, order_id: str, payment_id: int = 0) -> Result:
    return code, click_id, order_id, payment_id


def _prepare_result(result: Result) -> PrepareResponse:
    error, click_id, order_id, payment_id = result
    return PrepareResponse(
        click_trans_id=click_id,
        merchant_trans_id=order_id,
        merchant_prepare_id=payment_id,
        error=error[0],
        error_note=error[1],
    )


def _complete_result(result: Result) -> CompleteResponse:
    error, click_id, order_id, payment_id = result
    return CompleteResponse(
        click_trans_id=click_id,
        merchant_trans_id=order_id,
        merchant_confirm_id=payment_id,
        error=error[0],
        error_note=error[1],
    )


def process_prepare(
    session: Session, fields: PrepareFields, settings: Settings, cache: ProductCache
) -> PrepareResponse:
    click_id = _positive_int(fields.click_trans_id) or 0
    order_id = fields.merchant_trans_id
    signed = prepare_signature(fields.model_dump(), settings.click_secret_key or "")
    if not secrets.compare_digest(fields.sign_string.lower(), signed):
        return _prepare_result(_error(SIGNATURE_ERROR, click_id, order_id))
    if fields.service_id != settings.click_service_id or fields.action != "0":
        return _prepare_result(_error(ACTION_ERROR, click_id, order_id))
    external_id = _positive_int(fields.click_trans_id)
    local_order_id = _positive_int(order_id)
    amount = _amount(fields.amount)
    if external_id is None or local_order_id is None:
        return _prepare_result(_error(ORDER_ERROR, click_id, order_id))
    if amount is None:
        return _prepare_result(_error(AMOUNT_ERROR, click_id, order_id))

    order = session.scalar(select(Order).where(Order.id == local_order_id).with_for_update())
    if order is None:
        session.rollback()
        return _prepare_result(_error(ORDER_ERROR, click_id, order_id))
    if not amount_matches_order(order, amount):
        session.rollback()
        return _prepare_result(_error(AMOUNT_ERROR, click_id, order_id))
    if order.status != "pending":
        session.rollback()
        code = CANCELLED_ERROR if order.status == "cancelled" else PAID_ERROR
        return _prepare_result(_error(code, click_id, order_id))
    now = datetime.now(UTC)
    if order.expires_at <= now:
        restored = cancel_locked_order(session, order)
        session.commit()
        if restored:
            cache.invalidate()
        return _prepare_result(_error(CANCELLED_ERROR, click_id, order_id))

    existing = session.scalar(
        select(PaymentTransaction)
        .where(
            PaymentTransaction.provider == "click",
            PaymentTransaction.external_id == fields.click_trans_id,
        )
        .with_for_update()
    )
    if existing is not None:
        same_request = existing.order_id == local_order_id and existing.amount == amount
        if not same_request:
            return _prepare_result(_error(AMOUNT_ERROR, click_id, order_id))
        if existing.request_status == "failed":
            return _prepare_result(_error(CANCELLED_ERROR, click_id, order_id, existing.id))
        if existing.request_status == "success":
            return _prepare_result(_error(PAID_ERROR, click_id, order_id, existing.id))
        session.rollback()
        return _prepare_result(((0, "Success"), click_id, order_id, existing.id))

    transaction = PaymentTransaction(
        order_id=order.id,
        provider="click",
        external_id=fields.click_trans_id,
        amount=amount,
        request_status="pending",
        status="prepared",
        response_status="pending",
        processed_at=None,
    )
    session.add(transaction)
    try:
        session.flush()
        response = _prepare_result(((0, "Success"), click_id, order_id, transaction.id))
        session.commit()
        return response
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.provider == "click",
                PaymentTransaction.external_id == fields.click_trans_id,
            )
        )
        if existing and existing.order_id == local_order_id and existing.amount == amount:
            return _prepare_result(((0, "Success"), click_id, order_id, existing.id))
        return _prepare_result(_error(AMOUNT_ERROR, click_id, order_id))


def process_complete(
    session: Session,
    fields: CompleteFields,
    settings: Settings,
    cache: ProductCache,
) -> CompleteResponse:
    click_id = _positive_int(fields.click_trans_id) or 0
    order_id = fields.merchant_trans_id
    signed = complete_signature(fields.model_dump(), settings.click_secret_key or "")
    if not secrets.compare_digest(fields.sign_string.lower(), signed):
        return _complete_result(_error(SIGNATURE_ERROR, click_id, order_id))
    if fields.service_id != settings.click_service_id or fields.action != "1":
        return _complete_result(_error(ACTION_ERROR, click_id, order_id))
    external_id = _positive_int(fields.click_trans_id)
    local_order_id = _positive_int(order_id)
    prepare_id = _positive_int(fields.merchant_prepare_id)
    amount = _amount(fields.amount)
    error = _signed_int(fields.error)
    paydoc_id = _positive_int(fields.click_paydoc_id)
    if external_id is None or local_order_id is None:
        return _complete_result(_error(ORDER_ERROR, click_id, order_id))
    if amount is None:
        return _complete_result(_error(AMOUNT_ERROR, click_id, order_id))
    if prepare_id is None:
        return _complete_result(_error(PREPARE_ERROR, click_id, order_id))
    if error is None or error > 0 or (error == 0 and paydoc_id is None):
        return _complete_result(_error(ACTION_ERROR, click_id, order_id))

    order = session.scalar(select(Order).where(Order.id == local_order_id).with_for_update())
    if order is None:
        session.rollback()
        return _complete_result(_error(ORDER_ERROR, click_id, order_id))
    transaction = session.scalar(
        select(PaymentTransaction)
        .where(
            PaymentTransaction.provider == "click",
            PaymentTransaction.external_id == fields.click_trans_id,
        )
        .with_for_update()
    )
    if transaction is None or transaction.id != prepare_id:
        session.rollback()
        return _complete_result(_error(PREPARE_ERROR, click_id, order_id))
    if transaction.order_id != order.id or transaction.amount != amount:
        session.rollback()
        return _complete_result(_error(AMOUNT_ERROR, click_id, order_id))
    if transaction.status == "processed":
        code = PAID_ERROR if transaction.request_status == "success" else CANCELLED_ERROR
        session.rollback()
        return _complete_result(_error(code, click_id, order_id, transaction.id))
    if transaction.status != "prepared" or not amount_matches_order(order, amount):
        session.rollback()
        return _complete_result(_error(AMOUNT_ERROR, click_id, order_id, transaction.id))

    now = datetime.now(UTC)
    if error < 0:
        restored = order.status == "pending" and cancel_locked_order(session, order)
        transaction.request_status = "failed"
    elif order.status == "pending" and order.expires_at > now:
        pay_locked_order(order)
        transaction.request_status = "success"
        restored = False
    else:
        restored = order.status == "pending" and cancel_locked_order(session, order)
        transaction.request_status = "success"
        transaction.recovery_status = "manual_review"
        transaction.recovery_note = (
            "Click confirmed payment after the order became terminal; reconcile funds manually."
        )

    transaction.status = "processed"
    transaction.response_status = order.status
    transaction.click_paydoc_id = paydoc_id
    transaction.processed_at = now
    session.commit()
    if restored:
        cache.invalidate()
    if error < 0:
        return _complete_result(_error(CANCELLED_ERROR, click_id, order_id, transaction.id))
    return _complete_result(((0, "Success"), click_id, order_id, transaction.id))
