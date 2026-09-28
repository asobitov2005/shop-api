"""Add simulated task callback transactions."""

import sqlalchemy as sa

from alembic import op

revision = "0003_payment_transactions"
down_revision = "0002_uzs_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=24), nullable=False, server_default="simulated"),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="UZS"),
        sa.Column("request_status", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("response_status", sa.String(length=16), nullable=False),
        sa.Column("click_paydoc_id", sa.BigInteger(), nullable=True),
        sa.Column("recovery_status", sa.String(length=24), nullable=False, server_default="none"),
        sa.Column("recovery_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "external_id", name="uq_payment_provider_external_id"),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        sa.CheckConstraint("currency = 'UZS'", name="ck_payments_currency_uzs"),
        sa.CheckConstraint(
            "request_status IN ('pending', 'success', 'failed')", name="ck_payment_request_status"
        ),
        sa.CheckConstraint(
            "status IN ('prepared', 'processed')", name="ck_payment_internal_status"
        ),
        sa.CheckConstraint(
            "response_status IN ('pending', 'paid', 'cancelled')",
            name="ck_payment_response_status",
        ),
        sa.CheckConstraint(
            "recovery_status IN ('none', 'manual_review')", name="ck_payment_recovery_status"
        ),
    )
    op.create_index("ix_payment_transactions_order_id", "payment_transactions", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_transactions_order_id", table_name="payment_transactions")
    op.drop_table("payment_transactions")
