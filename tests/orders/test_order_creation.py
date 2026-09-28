from decimal import Decimal

import pytest
from sqlalchemy import select

from app.orders.models import Order, OrderItem
from app.products.models import Product


def test_order_combines_duplicates_and_snapshots_server_price(client, db_session, seed_products):
    product = seed_products(Product(name="Tea", price=Decimal("2.50"), stock=8))[0]
    db_session.commit()

    response = client.post(
        "/orders",
        json={
            "items": [
                {"product_id": product.id, "quantity": 2},
                {"product_id": product.id, "quantity": 3},
            ]
        },
    )

    assert response.status_code == 201
    order = db_session.scalar(select(Order))
    item = db_session.scalar(select(OrderItem))
    db_session.refresh(product)
    assert response.json()["status"] == "pending"
    assert response.json()["total_amount"] == "12.50"
    assert response.json()["payment_url"] is None
    assert item.quantity == 5
    assert item.unit_price == Decimal("2.50")
    assert product.stock == 3
    assert order.expires_at > order.created_at


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"product_id": 1, "quantity": 0}],
        [{"product_id": 1, "quantity": -1}],
        [{"product_id": 1, "quantity": 1.5}],
    ],
)
def test_order_rejects_empty_or_non_positive_integer_quantities(client, items):
    assert client.post("/orders", json={"items": items}).status_code == 422


def test_insufficient_stock_rolls_back_every_item(client, db_session, seed_products):
    a, b = seed_products(
        Product(name="A", price=Decimal("1.00"), stock=4),
        Product(name="B", price=Decimal("1.00"), stock=1),
    )
    db_session.commit()
    a_id, b_id = a.id, b.id

    response = client.post(
        "/orders",
        json={
            "items": [
                {"product_id": a_id, "quantity": 2},
                {"product_id": b_id, "quantity": 2},
            ]
        },
    )

    assert response.status_code == 409
    with db_session.get_bind().connect() as connection:
        stocks = connection.execute(select(Product.id, Product.stock).order_by(Product.id)).all()
        order_count = connection.execute(select(Order.id)).all()
    assert stocks == [(a_id, 4), (b_id, 1)]
    assert order_count == []


def test_missing_product_returns_not_found(client, db_session):
    response = client.post("/orders", json={"items": [{"product_id": 999, "quantity": 1}]})
    assert response.status_code == 404
    assert db_session.scalar(select(Order)) is None


def test_order_reservation_invalidates_cached_stock(client, db_session, seed_products):
    product = seed_products(Product(name="Milk", price=Decimal("1.00"), stock=3))[0]
    db_session.commit()
    assert client.get("/products").json()["items"][0]["stock"] == 3

    response = client.post("/orders", json={"items": [{"product_id": product.id, "quantity": 1}]})

    assert response.status_code == 201
    assert client.get("/products").json()["items"][0]["stock"] == 2
