from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.orders.models import Order
from app.payments.models import PaymentTransaction
from app.products.models import Product
from tests.payments.helpers import make_order, send_callback


def test_concurrent_identical_callbacks_create_one_transaction(client, db_session, redis_client):
    order_id, product_id = make_order(db_session, redis_client)
    payload = {
        "transaction_id": "txn-concurrent",
        "order_id": order_id,
        "amount": "12.50",
        "status": "success",
    }

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(lambda _: send_callback(client, payload), range(5)))

    assert [response.status_code for response in responses] == [200] * 5
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "paid"
    assert db_session.get(Product, product_id).stock == 2
    assert (
        len(
            db_session.scalars(
                select(PaymentTransaction).where(PaymentTransaction.external_id == "txn-concurrent")
            ).all()
        )
        == 1
    )
