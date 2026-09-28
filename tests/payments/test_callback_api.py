import hashlib
import hmac

from sqlalchemy import select

from app.orders.models import Order, OrderItem
from app.payments.models import PaymentTransaction
from app.products.models import Product
from tests.payments.helpers import SECRET, make_order, send_callback


def test_valid_success_and_five_retries_settle_once(client, db_session, redis_client):
    order_id, product_id = make_order(db_session, redis_client)
    payload = {
        "transaction_id": "txn-1",
        "order_id": order_id,
        "amount": "12.50",
        "status": "success",
    }

    results = [send_callback(client, payload) for _ in range(5)]

    assert [response.status_code for response in results] == [200] * 5
    assert len({response.json()["status"] for response in results}) == 1
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "paid"
    assert db_session.get(Product, product_id).stock == 2
    transaction = db_session.scalar(
        select(PaymentTransaction).where(PaymentTransaction.external_id == "txn-1")
    )
    assert transaction.currency == "UZS"
    assert transaction.processed_at is not None


def test_invalid_signature_and_wrong_amount_do_not_change_state(client, db_session, redis_client):
    order_id, product_id = make_order(db_session, redis_client)
    payload = {
        "transaction_id": "txn-invalid",
        "order_id": order_id,
        "amount": "12.50",
        "status": "success",
    }

    bad_signature = send_callback(client, payload, "0" * 64)
    wrong_amount = send_callback(
        client, {**payload, "transaction_id": "txn-amount", "amount": "12.51"}
    )

    assert bad_signature.status_code == 401
    assert wrong_amount.status_code == 409
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "pending"
    assert db_session.get(Product, product_id).stock == 2
    assert db_session.scalar(select(PaymentTransaction)) is None


def test_malformed_payload_is_rejected_after_valid_signature(client):
    raw = b"{bad json"
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post(
        "/payments/callback",
        content=raw,
        headers={"Content-Type": "application/json", "X-Signature": signature},
    )
    assert response.status_code == 422


def test_reused_transaction_id_with_changed_business_data_conflicts(
    client, db_session, redis_client
):
    order_id, _ = make_order(db_session, redis_client)
    payload = {
        "transaction_id": "txn-reuse",
        "order_id": order_id,
        "amount": "12.50",
        "status": "success",
    }
    assert send_callback(client, payload).status_code == 200

    changed = send_callback(client, {**payload, "amount": "12.51"})

    assert changed.status_code == 409
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "paid"
    assert db_session.scalar(select(OrderItem).where(OrderItem.order_id == order_id)).quantity == 1


def test_failed_callback_cancels_and_invalidates_product_cache(client, db_session, redis_client):
    order_id, product_id = make_order(db_session, redis_client)
    payload = {
        "transaction_id": "txn-failed",
        "order_id": order_id,
        "amount": "12.50",
        "status": "failed",
    }

    response = send_callback(client, payload)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "cancelled"
    assert db_session.get(Product, product_id).stock == 3
    assert int(redis_client.get("products:list:version")) == 2


def test_unknown_order_returns_not_found(client):
    response = send_callback(
        client,
        {"transaction_id": "txn-unknown", "order_id": 999, "amount": "1.00", "status": "success"},
    )
    assert response.status_code == 404


def test_missing_signature_is_unauthorized(client):
    response = client.post("/payments/callback", content=b"{}")
    assert response.status_code == 401


def test_distinct_success_after_paid_order_conflicts(client, db_session, redis_client):
    order_id, product_id = make_order(db_session, redis_client)
    payload = {
        "transaction_id": "txn-first",
        "order_id": order_id,
        "amount": "12.50",
        "status": "success",
    }
    assert send_callback(client, payload).status_code == 200

    second = send_callback(client, {**payload, "transaction_id": "txn-second"})

    assert second.status_code == 409
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "paid"
    assert db_session.get(Product, product_id).stock == 2
    assert (
        db_session.scalar(
            select(PaymentTransaction).where(PaymentTransaction.external_id == "txn-second")
        )
        is None
    )


def test_reused_transaction_id_cannot_move_to_another_order(client, db_session, redis_client):
    first_order_id, _ = make_order(db_session, redis_client)
    second_order_id, second_product_id = make_order(db_session, redis_client)
    payload = {
        "transaction_id": "txn-cross-order",
        "order_id": first_order_id,
        "amount": "12.50",
        "status": "success",
    }
    assert send_callback(client, payload).status_code == 200

    changed = send_callback(client, {**payload, "order_id": second_order_id})

    assert changed.status_code == 409
    db_session.expire_all()
    assert db_session.get(Order, second_order_id).status == "pending"
    assert db_session.get(Product, second_product_id).stock == 2
