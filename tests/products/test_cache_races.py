from decimal import Decimal

from sqlalchemy.orm import Session

from app.products.cache import ProductCache
from app.products.models import Product


def test_old_catalog_read_is_not_cached_after_stock_invalidation(
    client, db_session, seed_products, test_engine, monkeypatch
):
    product = seed_products(Product(name="Milk", price=Decimal("1.00"), stock=3))[0]
    product_id = product.id
    db_session.commit()
    original_set = ProductCache.set

    def mutation_before_cache_write(cache, page, page_size, payload, *args, **kwargs):
        with Session(test_engine) as mutation_session:
            current = mutation_session.get(Product, product_id)
            current.stock = 2
            mutation_session.commit()
        cache.invalidate()
        original_set(cache, page, page_size, payload, *args, **kwargs)

    monkeypatch.setattr(ProductCache, "set", mutation_before_cache_write)

    first = client.get("/products")
    second = client.get("/products")

    assert first.json()["items"][0]["stock"] == 3
    assert second.json()["items"][0]["stock"] == 2
