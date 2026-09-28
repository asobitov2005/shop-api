from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_payment_provider_external_id"),
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        CheckConstraint("currency = 'UZS'", name="ck_payments_currency_uzs"),
        CheckConstraint(
            "request_status IN ('pending', 'success', 'failed')", name="ck_payment_request_status"
        ),
        CheckConstraint("status IN ('prepared', 'processed')", name="ck_payment_internal_status"),
        CheckConstraint(
            "response_status IN ('pending', 'paid', 'cancelled')",
            name="ck_payment_response_status",
        ),
        CheckConstraint(
            "recovery_status IN ('none', 'manual_review')", name="ck_payment_recovery_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(24), nullable=False, default="simulated")
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="UZS", server_default=text("'UZS'")
    )
    request_status: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processed")
    response_status: Mapped[str] = mapped_column(String(16), nullable=False)
    click_paydoc_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recovery_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="none", server_default=text("'none'")
    )
    recovery_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
