from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orders.models import Order
from app.orders.transitions import cancel_locked_order
from app.products.cache import ProductCache


def expire_pending_orders(
    session: Session,
    cache: ProductCache,
    *,
    now: datetime | None = None,
    batch_size: int = 100,
) -> int:
    current_time = now or datetime.now(UTC)
    due_orders = session.scalars(
        select(Order)
        .where(Order.status == "pending", Order.expires_at <= current_time)
        .order_by(Order.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    if not due_orders:
        session.rollback()
        return 0

    cancelled = sum(cancel_locked_order(session, order) for order in due_orders)
    session.commit()
    if cancelled:
        cache.invalidate()
    return cancelled
