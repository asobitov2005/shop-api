from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orders.models import Order, OrderItem
from app.products.models import Product


def cancel_locked_order(session: Session, order: Order) -> bool:
    if order.status != "pending":
        return False
    rows = session.scalars(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.product_id)
    ).all()
    products = session.scalars(
        select(Product)
        .where(Product.id.in_([row.product_id for row in rows]))
        .order_by(Product.id)
        .with_for_update()
    ).all()
    by_id = {product.id: product for product in products}
    for item in rows:
        by_id[item.product_id].stock += item.quantity
    order.status = "cancelled"
    return True


def pay_locked_order(order: Order) -> bool:
    if order.status != "pending":
        return False
    order.status = "paid"
    return True
