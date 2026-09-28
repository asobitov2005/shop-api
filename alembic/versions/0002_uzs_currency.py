"""Mark product prices and order totals as Uzbek so'm."""

import sqlalchemy as sa

from alembic import op

revision = "0002_uzs_currency"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'UZS'"), nullable=False),
    )
    op.create_check_constraint("ck_products_currency_uzs", "products", "currency = 'UZS'")
    op.add_column(
        "orders",
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'UZS'"), nullable=False),
    )
    op.create_check_constraint("ck_orders_currency_uzs", "orders", "currency = 'UZS'")


def downgrade() -> None:
    op.drop_constraint("ck_orders_currency_uzs", "orders", type_="check")
    op.drop_column("orders", "currency")
    op.drop_constraint("ck_products_currency_uzs", "products", type_="check")
    op.drop_column("products", "currency")
