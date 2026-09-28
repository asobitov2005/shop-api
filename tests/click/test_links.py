from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.payments.click.links import payment_link
from app.products.models import Product


def test_payment_link_formats_uzs_amount_and_encodes_order_and_return_url():
    settings = Settings(
        click_merchant_id="merchant 1",
        click_service_id="service&2",
        click_secret_key="private",
        click_merchant_user_id="user",
        click_return_url="https://shop.example/return?from=click",
    )

    link = payment_link(83, Decimal("1250.5"), settings)
    parsed = urlparse(link)

    assert parsed.scheme == "https"
    assert parsed.netloc == "my.click.uz"
    assert parsed.path == "/services/pay"
    assert parse_qs(parsed.query) == {
        "merchant_id": ["merchant 1"],
        "service_id": ["service&2"],
        "amount": ["1250.50"],
        "transaction_param": ["83"],
        "return_url": ["https://shop.example/return?from=click"],
    }
    assert "private" not in link
    assert "user" not in link


def test_payment_link_omits_unconfigured_return_url():
    settings = Settings(
        click_merchant_id="merchant",
        click_service_id="service",
        click_secret_key="private",
        click_merchant_user_id="user",
    )

    link = payment_link(7, Decimal("100.00"), settings)

    assert parse_qs(urlparse(link).query) == {
        "merchant_id": ["merchant"],
        "service_id": ["service"],
        "amount": ["100.00"],
        "transaction_param": ["7"],
    }


def test_payment_link_is_absent_without_click_configuration():
    assert payment_link(7, Decimal("100.00"), Settings()) is None


def test_partial_click_configuration_fails_clearly():
    with pytest.raises(ValidationError, match="must be configured together"):
        Settings(click_merchant_id="merchant")


def test_order_response_contains_click_payment_link(client, db_session, seed_products):
    settings = Settings(
        click_merchant_id="merchant",
        click_service_id="service",
        click_secret_key="private",
        click_merchant_user_id="user",
    )
    client.app.state.settings = settings
    product = seed_products(Product(name="Tea", price=Decimal("15000.00"), stock=2))[0]
    db_session.commit()

    response = client.post("/orders", json={"items": [{"product_id": product.id, "quantity": 1}]})

    assert response.status_code == 201
    assert parse_qs(urlparse(response.json()["payment_url"]).query) == {
        "merchant_id": ["merchant"],
        "service_id": ["service"],
        "amount": ["15000.00"],
        "transaction_param": [str(response.json()["id"])],
    }
