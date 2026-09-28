from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.orders.schemas import OrderCreate, OrderItemInput
from app.orders.service import create_order
from app.products.cache import ProductCache
from app.products.models import Product
from app.worker.expiry import expire_pending_orders


def make_order(db_session, redis_client):
    product = Product(name="Expiring item", price=Decimal("7.25"), stock=2)
    db_session.add(product)
    db_session.commit()
    order = create_order(
        db_session,
        OrderCreate(items=[OrderItemInput(product_id=product.id, quantity=1)]),
        ProductCache(redis_client),
    )
    return order, product


def test_expired_pending_order_restores_stock_once(db_session, redis_client):
    order, product = make_order(db_session, redis_client)
    order.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    cache = ProductCache(redis_client)

    first = expire_pending_orders(db_session, cache)
    second = expire_pending_orders(db_session, cache)

    db_session.refresh(order)
    db_session.refresh(product)
    assert first == 1
    assert second == 0
    assert order.status == "cancelled"
    assert product.stock == 2
    assert int(redis_client.get("products:list:version")) == 2


def test_fresh_and_paid_orders_are_not_expired(db_session, redis_client):
    pending, _ = make_order(db_session, redis_client)
    paid, _ = make_order(db_session, redis_client)
    paid.status = "paid"
    paid.expires_at = datetime.now(UTC) - timedelta(minutes=20)
    db_session.commit()

    expired = expire_pending_orders(db_session, ProductCache(redis_client))

    db_session.refresh(pending)
    db_session.refresh(paid)
    assert expired == 0
    assert pending.status == "pending"
    assert paid.status == "paid"


def test_two_workers_restore_expired_order_once(db_session, redis_client, test_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    order, product = make_order(db_session, redis_client)
    order.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    barrier = Barrier(2)

    def expire():
        with Session(bind=test_engine, expire_on_commit=False) as session:
            barrier.wait()
            return expire_pending_orders(session, ProductCache(redis_client))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: expire(), range(2)))

    db_session.refresh(order)
    db_session.refresh(product)
    assert sum(results) == 1
    assert order.status == "cancelled"
    assert product.stock == 2
    assert int(redis_client.get("products:list:version")) == 2


def test_callback_racing_expiry_cancels_and_releases_once(
    client, db_session, redis_client, test_engine
):
    import hashlib
    import hmac
    import json
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    order, product = make_order(db_session, redis_client)
    order.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    body = json.dumps(
        {
            "transaction_id": "txn-expiry-race",
            "order_id": order.id,
            "amount": "7.25",
            "status": "success",
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(b"local-task-webhook-secret", body, hashlib.sha256).hexdigest()
    barrier = Barrier(2)

    def callback():
        barrier.wait()
        return client.post(
            "/payments/callback",
            content=body,
            headers={"Content-Type": "application/json", "X-Signature": signature},
        )

    def expire():
        with Session(bind=test_engine, expire_on_commit=False) as session:
            barrier.wait()
            return expire_pending_orders(session, ProductCache(redis_client))

    with ThreadPoolExecutor(max_workers=2) as pool:
        callback_future = pool.submit(callback)
        expiry_future = pool.submit(expire)
        response, expired = callback_future.result(), expiry_future.result()

    db_session.refresh(order)
    db_session.refresh(product)
    assert response.status_code == 409
    assert expired in (0, 1)
    assert order.status == "cancelled"
    assert product.stock == 2
    assert int(redis_client.get("products:list:version")) == 2
