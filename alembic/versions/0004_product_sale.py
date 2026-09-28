"""Set catalog sale prices to 1,000 UZS and preserve discount details."""

import sqlalchemy as sa

from alembic import op

revision = "0004_product_sale"
down_revision = "0003_payment_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("original_price", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.execute(
        "UPDATE products SET original_price = GREATEST(price, 1000), "
        "discount_amount = GREATEST(price - 1000, 0), price = 1000"
    )
    op.alter_column("products", "original_price", nullable=False)
    op.create_check_constraint(
        "ck_products_discount_valid",
        "products",
        "discount_amount <= original_price AND price = original_price - discount_amount",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_discount_valid", "products", type_="check")
    op.execute("UPDATE products SET price = original_price")
    op.drop_column("products", "discount_amount")
    op.drop_column("products", "original_price")
