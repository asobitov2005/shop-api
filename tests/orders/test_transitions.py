from decimal import Decimal

from app.orders.models import Order, OrderItem
from app.orders.transitions import cancel_locked_order
from app.products.models import Product


def test_cancelling_pending_order_restores_stock_once(db_session):
    product = Product(name="Coffee", price=Decimal("4.00"), stock=2)
    db_session.add(product)
    db_session.flush()
    order = Order(status="pending", total_amount=Decimal("4.00"))
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderItem(order_id=order.id, product_id=product.id, quantity=1, unit_price=product.price)
    )
    db_session.flush()
    locked = db_session.get(Order, order.id, with_for_update=True)

    assert cancel_locked_order(db_session, locked) is True
    assert cancel_locked_order(db_session, locked) is False
    db_session.flush()
    assert product.stock == 3
