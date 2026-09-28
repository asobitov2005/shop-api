from decimal import Decimal

from app.core.config import Settings
from app.payments.click.signatures import complete_signature, prepare_signature
from app.products.models import Product


def click_settings(client):
    settings = Settings(
        click_merchant_id="merchant",
        click_service_id="service",
        click_secret_key="secret",
        click_merchant_user_id="user",
    )
    client.app.state.settings = settings
    return settings


def order(client, db_session):
    product = Product(name="Tea", price=Decimal("12000.00"), stock=4)
    db_session.add(product)
    db_session.commit()
    response = client.post("/orders", json={"items": [{"product_id": product.id, "quantity": 1}]})
    assert response.status_code == 201
    return response.json()["id"], product.id


def prepare(client, order_id, settings, *, transaction_id="101", amount="12000.00"):
    fields = {
        "click_trans_id": transaction_id,
        "service_id": settings.click_service_id,
        "click_user_id": "click-user",
        "merchant_trans_id": str(order_id),
        "amount": amount,
        "action": "0",
        "sign_time": "2026-09-28 12:30:00",
    }
    fields["sign_string"] = prepare_signature(fields, settings.click_secret_key)
    return client.post("/payments/click/callback", data=fields)


def complete(
    client,
    order_id,
    settings,
    prepare_id,
    *,
    transaction_id="101",
    amount="12000.00",
    error="0",
    paydoc_id="9001",
):
    fields = {
        "click_trans_id": transaction_id,
        "service_id": settings.click_service_id,
        "click_user_id": "click-user",
        "merchant_trans_id": str(order_id),
        "merchant_prepare_id": str(prepare_id),
        "amount": amount,
        "action": "1",
        "error": error,
        "error_note": "",
        "click_paydoc_id": paydoc_id,
        "sign_time": "2026-09-28 12:31:00",
    }
    fields["sign_string"] = complete_signature(fields, settings.click_secret_key)
    return client.post("/payments/click/callback", data=fields)
