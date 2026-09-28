from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orders.models import Order, OrderItem
from app.orders.schemas import OrderCreate
from app.products.cache import ProductCache
from app.products.models import Product


def create_order(session: Session, payload: OrderCreate, cache: ProductCache) -> Order:
    quantities: dict[int, int] = {}
    for item in payload.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    products = session.scalars(
        select(Product)
        .where(Product.id.in_(sorted(quantities)))
        .order_by(Product.id)
        .with_for_update()
    ).all()
    by_id = {product.id: product for product in products}
    if by_id.keys() != quantities.keys():
        session.rollback()
        raise HTTPException(status_code=404, detail="Product not found")
    for product_id, quantity in quantities.items():
        if by_id[product_id].stock < quantity:
            session.rollback()
            raise HTTPException(status_code=409, detail="Insufficient stock")
    created = datetime.now(UTC)
    total = sum((by_id[pid].price * qty for pid, qty in quantities.items()), Decimal("0.00"))
    order = Order(
        status="pending",
        total_amount=total,
        created_at=created,
        expires_at=created + timedelta(minutes=15),
    )
    session.add(order)
    session.flush()
    for product_id, quantity in quantities.items():
        product = by_id[product_id]
        product.stock -= quantity
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product_id,
                quantity=quantity,
                unit_price=product.price,
            )
        )
    session.commit()
    cache.invalidate()
    return order
