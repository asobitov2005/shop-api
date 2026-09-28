from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.orders.models import Order
from app.orders.schemas import OrderCreate
from app.orders.service import create_order
from app.products.cache import ProductCache
from app.products.models import Product


def test_only_one_concurrent_order_can_reserve_last_unit(test_engine, redis_client):
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    with factory.begin() as session:
        product = Product(name="Last unit", price=Decimal("1.00"), stock=1)
        session.add(product)
        session.flush()
        product_id = product.id
    barrier = Barrier(2)

    def buy() -> str:
        with factory() as session:
            barrier.wait()
            try:
                create_order(
                    session,
                    OrderCreate(items=[{"product_id": product_id, "quantity": 1}]),
                    ProductCache(redis_client),
                )
                return "created"
            except HTTPException as error:
                assert error.status_code == 409
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: buy(), range(2)))
    assert sorted(outcomes) == ["created", "rejected"]
    with factory() as session:
        product = session.get(Product, product_id)
        assert product.stock == 0
        assert session.scalar(select(Order.id)) is not None
        assert len(session.scalars(select(Order.id)).all()) == 1
