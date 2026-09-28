from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import seed as seed_module
from app.products.models import Product


def test_seed_creates_uzbek_catalog_with_uzs_prices(test_engine, test_settings, monkeypatch):
    monkeypatch.setattr(
        seed_module,
        "get_settings",
        lambda: test_settings.model_copy(update={"database_url": test_settings.test_database_url}),
    )

    seed_module.seed()
    seed_module.seed()

    with Session(test_engine) as session:
        products = session.scalars(select(Product).order_by(Product.name)).all()

    assert [
        (product.name, product.price, product.currency, product.stock) for product in products
    ] == [
        ("Asal", Decimal("45000.00"), "UZS", 30),
        ("Choy", Decimal("15000.00"), "UZS", 100),
        ("Qahva", Decimal("25000.00"), "UZS", 50),
    ]


def test_database_rejects_non_uzs_product_and_order_currency(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.orders.models import Order

    invalid_rows = (
        Product(name="Invalid product", price=1, stock=1, currency="USD"),
        Order(status="pending", total_amount=1, currency="USD"),
    )
    for row in invalid_rows:
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.add(row)
                db_session.flush()


def test_seed_invalidates_empty_product_page_once_after_insert(
    client, redis_client, test_settings, monkeypatch
):
    from app.products.cache import VERSION_KEY

    monkeypatch.setattr(
        seed_module,
        "get_settings",
        lambda: test_settings.model_copy(
            update={
                "database_url": test_settings.test_database_url,
                "redis_url": test_settings.test_redis_url,
            }
        ),
    )
    assert client.get("/products").json()["items"] == []

    seed_module.seed()

    products = client.get("/products").json()["items"]
    assert [product["name"] for product in products] == ["Choy", "Qahva", "Asal"]
    assert all(product["currency"] == "UZS" for product in products)
    assert redis_client.get(VERSION_KEY) == "1"

    seed_module.seed()
    assert redis_client.get(VERSION_KEY) == "1"
