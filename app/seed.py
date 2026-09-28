from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import make_session_factory
from app.products.models import Product

SEED_PRODUCTS = (
    ("Choy", Decimal("15000.00"), 100),
    ("Qahva", Decimal("25000.00"), 50),
    ("Asal", Decimal("45000.00"), 30),
)


def seed() -> None:
    factory = make_session_factory(get_settings().database_url)
    with factory.begin() as session:
        for name, price, stock in SEED_PRODUCTS:
            exists = session.scalar(select(Product.id).where(Product.name == name))
            if exists is None:
                session.add(Product(name=name, price=price, stock=stock))
    factory.kw["bind"].dispose()


if __name__ == "__main__":
    seed()
