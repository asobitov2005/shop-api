import hashlib
import hmac
import json
from decimal import Decimal

from app.orders.schemas import OrderCreate, OrderItemInput
from app.orders.service import create_order
from app.products.cache import ProductCache
from app.products.models import Product

SECRET = "local-task-webhook-secret"


def make_order(db_session, redis_client):
    product = Product(name="Test item", price=Decimal("12.50"), stock=3)
    db_session.add(product)
    db_session.commit()
    order = create_order(
        db_session,
        OrderCreate(items=[OrderItemInput(product_id=product.id, quantity=1)]),
        ProductCache(redis_client),
    )
    return order.id, product.id


def send_callback(client, body, signature=None):
    raw = json.dumps(body, separators=(",", ":")).encode()
    signature = signature or hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/payments/callback",
        content=raw,
        headers={"Content-Type": "application/json", "X-Signature": signature},
    )
