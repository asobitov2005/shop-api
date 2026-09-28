from decimal import Decimal

import redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import make_session_factory
from app.products.cache import ProductCache
from app.products.models import Product

SEED_PRODUCTS = (
    ("Choy", Decimal("1000.00"), Decimal("14000.00"), Decimal("15000.00"), 100),
    ("Qahva", Decimal("1000.00"), Decimal("24000.00"), Decimal("25000.00"), 50),
    ("Asal", Decimal("1000.00"), Decimal("44000.00"), Decimal("45000.00"), 30),
)


def seed() -> None:
    settings = get_settings()
    factory = make_session_factory(settings.database_url)
    inserted = False
    try:
        with factory.begin() as session:
            for name, price, discount, original_price, stock in SEED_PRODUCTS:
                exists = session.scalar(select(Product.id).where(Product.name == name))
                if exists is None:
                    session.add(
                        Product(
                            name=name,
                            price=price,
                            discount_amount=discount,
                            original_price=original_price,
                            stock=stock,
                        )
                    )
                    inserted = True
    finally:
        factory.kw["bind"].dispose()

    if inserted:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            ProductCache(client).invalidate()
        finally:
            client.close()


if __name__ == "__main__":
    seed()
