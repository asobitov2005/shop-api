from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.orders.models import Order
from app.payments.models import PaymentTransaction
from app.products.cache import ProductCache
from app.products.models import Product
from app.worker import expiry
from app.worker.expiry import expire_pending_orders
from tests.click.shop_helpers import click_settings, complete, order, prepare


def test_distinct_successful_attempt_after_order_paid_is_recorded_for_review(
    client, db_session, caplog
):
    settings = click_settings(client)
    order_id, product_id = order(client, db_session)
    first = prepare(client, order_id, settings, transaction_id="201")
    second = prepare(client, order_id, settings, transaction_id="202")
    assert first.json()["error"] == second.json()["error"] == 0

    assert (
        complete(
            client, order_id, settings, first.json()["merchant_prepare_id"], transaction_id="201"
        ).json()["error"]
        == 0
    )
    late = complete(
        client,
        order_id,
        settings,
        second.json()["merchant_prepare_id"],
        transaction_id="202",
    )

    assert late.json()["error"] == 0
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "paid"
    assert db_session.get(Product, product_id).stock == 3
    reviewed = db_session.scalar(
        select(PaymentTransaction).where(PaymentTransaction.external_id == "202")
    )
    assert reviewed.request_status == "success"
    assert reviewed.recovery_status == "manual_review"
    assert reviewed.recovery_note
    warning = next(record.message for record in caplog.records if "manual review" in record.message)
    assert str(order_id) in warning
    assert "202" in warning
    assert "9001" in warning
    assert "secret" not in warning


def test_successful_complete_after_expiry_cancels_locally_and_records_review(client, db_session):
    settings = click_settings(client)
    order_id, product_id = order(client, db_session)
    prepared = prepare(client, order_id, settings)
    prepare_id = prepared.json()["merchant_prepare_id"]
    db_session.execute(
        update(Order).where(Order.id == order_id).values(expires_at="2020-01-01T00:00:00+00:00")
    )
    db_session.commit()

    response = complete(client, order_id, settings, prepare_id)

    assert response.json()["error"] == 0
    db_session.expire_all()
    db_order = db_session.get(Order, order_id)
    transaction = db_session.scalar(select(PaymentTransaction))
    assert db_order.status == "cancelled"
    assert db_session.get(Product, product_id).stock == 4
    assert transaction.recovery_status == "manual_review"


def test_simultaneous_complete_calls_apply_one_payment_transition(client, db_session):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    settings = click_settings(client)
    order_id, product_id = order(client, db_session)
    prepared = prepare(client, order_id, settings)
    prepare_id = prepared.json()["merchant_prepare_id"]
    barrier = Barrier(2)

    def send_complete():
        barrier.wait()
        return complete(client, order_id, settings, prepare_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send_complete(), range(2)))

    assert sorted(response.json()["error"] for response in responses) == [-4, 0]
    db_session.expire_all()
    order_row = db_session.get(Order, order_id)
    payment = db_session.scalar(select(PaymentTransaction))
    product = db_session.get(Product, product_id)
    assert order_row.status == "paid"
    assert product.stock == 3 and product.stock >= 0
    assert payment.status == "processed"
    assert payment.request_status == "success"
    assert payment.recovery_status == "none"


def test_expiry_worker_wins_complete_race_and_records_manual_review(
    client, db_session, redis_client, test_engine, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    settings = click_settings(client)
    order_id, product_id = order(client, db_session)
    prepared = prepare(client, order_id, settings)
    prepare_id = prepared.json()["merchant_prepare_id"]
    db_session.execute(
        update(Order).where(Order.id == order_id).values(expires_at="2020-01-01T00:00:00+00:00")
    )
    db_session.commit()

    worker_locked_order = Event()
    finish_expiry = Event()
    original_cancel = expiry.cancel_locked_order

    def pause_after_lock(session, locked_order):
        worker_locked_order.set()
        if not finish_expiry.wait(timeout=5):
            raise TimeoutError("Test did not release expiry worker")
        return original_cancel(session, locked_order)

    monkeypatch.setattr(expiry, "cancel_locked_order", pause_after_lock)

    def run_expiry():
        with Session(bind=test_engine, expire_on_commit=False) as session:
            return expire_pending_orders(session, ProductCache(redis_client))

    def send_complete():
        completion_started.set()
        return complete(client, order_id, settings, prepare_id)

    completion_started = Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker = pool.submit(run_expiry)
        assert worker_locked_order.wait(timeout=5)
        completion = pool.submit(send_complete)
        assert completion_started.wait(timeout=5)
        finish_expiry.set()
        expired_count = worker.result(timeout=10)
        response = completion.result(timeout=10)

    assert expired_count == 1
    assert response.json()["error"] == 0
    db_session.expire_all()
    order_row = db_session.get(Order, order_id)
    payment = db_session.scalar(select(PaymentTransaction))
    product = db_session.get(Product, product_id)
    assert order_row.status == "cancelled"
    assert product.stock == 4 and product.stock >= 0
    assert payment.request_status == "success"
    assert payment.recovery_status == "manual_review"
    assert payment.recovery_note
