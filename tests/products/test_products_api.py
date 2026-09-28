from decimal import Decimal

from app.products.models import Product


def test_products_are_paginated_and_cached(client, db_session, seed_products):
    seed_products(
        *[Product(name=f"Product {i}", price=Decimal("3.25"), stock=i) for i in range(1, 5)]
    )
    db_session.commit()

    first = client.get("/products?page=1&page_size=2")
    again = client.get("/products?page=1&page_size=2")
    second = client.get("/products?page=2&page_size=2")

    assert first.status_code == 200
    assert first.json() == again.json()
    assert first.json()["total"] == 4
    assert first.json()["page"] == 1
    assert first.json()["page_size"] == 2
    assert [item["name"] for item in first.json()["items"]] == ["Product 1", "Product 2"]
    assert [item["name"] for item in second.json()["items"]] == ["Product 3", "Product 4"]
    assert first.json()["items"][0]["price"] == "3.25"
    assert first.json()["items"][0]["currency"] == "UZS"


def test_pagination_rejects_invalid_page_size(client):
    assert client.get("/products?page_size=0").status_code == 422
    assert client.get("/products?page_size=101").status_code == 422
