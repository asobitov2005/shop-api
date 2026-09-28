from sqlalchemy import select, update

from app.orders.models import Order
from app.payments.models import PaymentTransaction
from app.products.models import Product
from tests.click.shop_helpers import click_settings, complete, order, prepare


def test_distinct_successful_attempt_after_order_paid_is_recorded_for_review(client, db_session):
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
