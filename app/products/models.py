from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("stock >= 0", name="ck_products_stock_nonnegative"),
        CheckConstraint("currency = 'UZS'", name="ck_products_currency_uzs"),
        CheckConstraint(
            "original_price IS NULL OR "
            "(discount_amount <= original_price AND price = original_price - discount_amount)",
            name="ck_products_discount_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="UZS", server_default=text("'UZS'")
    )
    stock: Mapped[int] = mapped_column(nullable=False, default=0)
