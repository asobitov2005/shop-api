from sqlalchemy import select

from app.orders.models import Order
from app.payments.click.signatures import complete_signature, prepare_signature
from app.payments.models import PaymentTransaction
from app.products.models import Product
from tests.click.shop_helpers import click_settings, complete, order, prepare


def test_click_exposes_one_callback_url(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/payments/click/callback" in paths
    assert "/payments/click/prepare" not in paths
    assert "/payments/click/complete" not in paths


def test_official_click_field_sets_prepare_and_complete_order(client, db_session):
    settings = click_settings(client)
    order_id, _ = order(client, db_session)
    fields = {
        "click_trans_id": "901",
        "service_id": settings.click_service_id,
        "click_paydoc_id": "902",
        "merchant_trans_id": str(order_id),
        "amount": "12000.00",
        "action": "0",
        "error": "0",
        "error_note": "Success",
        "sign_time": "2026-09-28 12:30:00",
    }
    fields["sign_string"] = prepare_signature(fields, settings.click_secret_key)

    response = client.post("/payments/click/callback", data=fields)

    assert response.status_code == 200
    assert response.json()["error"] == 0
    prepare_id = response.json()["merchant_prepare_id"]
    assert prepare_id > 0
    assert db_session.scalar(select(PaymentTransaction)).order_id == order_id

    complete_fields = {
        **fields,
        "merchant_prepare_id": str(prepare_id),
        "action": "1",
        "sign_time": "2026-09-28 12:31:00",
    }
    complete_fields["sign_string"] = complete_signature(complete_fields, settings.click_secret_key)
    completed = client.post("/payments/click/callback", data=complete_fields)

    assert completed.status_code == 200
    assert completed.json()["error"] == 0
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "paid"


def test_prepare_retry_with_new_sign_time_keeps_same_local_id(client, db_session):
    settings = click_settings(client)
    order_id, _ = order(client, db_session)

    first = prepare(client, order_id, settings)
    retry_fields = {
        "click_trans_id": "101",
        "service_id": "service",
        "click_user_id": "click-user",
        "merchant_trans_id": str(order_id),
        "amount": "12000.00",
        "action": "0",
        "sign_time": "2026-09-28 12:35:00",
    }
    retry_fields["sign_string"] = prepare_signature(retry_fields, "secret")
    retry = client.post("/payments/click/callback", data=retry_fields)

    assert first.status_code == retry.status_code == 200
    assert first.json()["error"] == retry.json()["error"] == 0
    assert first.json()["merchant_prepare_id"] == retry.json()["merchant_prepare_id"]
    transaction = db_session.scalar(select(PaymentTransaction))
    assert transaction.status == "prepared"
    assert transaction.request_status == "pending"


def test_complete_settles_once_and_duplicate_reports_already_confirmed(client, db_session):
    settings = click_settings(client)
    order_id, product_id = order(client, db_session)
    prepared = prepare(client, order_id, settings)
    prepare_id = prepared.json()["merchant_prepare_id"]

    first = complete(client, order_id, settings, prepare_id)
    retry = complete(client, order_id, settings, prepare_id)

    assert first.status_code == retry.status_code == 200
    assert first.json()["error"] == 0
    assert retry.json()["error"] == -4
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "paid"
    assert db_session.get(Product, product_id).stock == 3
    transaction = db_session.scalar(select(PaymentTransaction))
    assert transaction.status == "processed"
    assert transaction.request_status == "success"
    assert transaction.click_paydoc_id == 9001


def test_invalid_signature_and_wrong_amount_do_not_create_payment(client, db_session):
    settings = click_settings(client)
    order_id, _ = order(client, db_session)
    bad = prepare(client, order_id, settings)
    bad_fields = {
        "click_trans_id": "102",
        "service_id": "service",
        "click_user_id": "click-user",
        "merchant_trans_id": str(order_id),
        "amount": "12000.00",
        "action": "0",
        "sign_time": "2026-09-28 12:30:00",
        "sign_string": "0" * 32,
    }
    invalid = client.post("/payments/click/callback", data=bad_fields)
    wrong_amount = prepare(client, order_id, settings, transaction_id="103", amount="1.00")

    assert bad.status_code == 200 and bad.json()["error"] == 0
    assert invalid.json()["error"] == -1
    assert wrong_amount.json()["error"] == -2
    assert len(db_session.scalars(select(PaymentTransaction)).all()) == 1


def test_prepare_rejects_wrong_service_and_unknownorder(client, db_session):
    settings = click_settings(client)
    order_id, _ = order(client, db_session)
    fields = {
        "click_trans_id": "104",
        "service_id": "other-service",
        "click_user_id": "click-user",
        "merchant_trans_id": str(order_id),
        "amount": "12000.00",
        "action": "0",
        "sign_time": "2026-09-28 12:30:00",
    }
    fields["sign_string"] = prepare_signature(fields, "secret")
    wrong_service = client.post("/payments/click/callback", data=fields)
    unknown_order = prepare(client, 999999, settings, transaction_id="105")

    assert wrong_service.status_code == 200 and wrong_service.json()["error"] == -3
    assert unknown_order.status_code == 200 and unknown_order.json()["error"] == -5
    assert db_session.scalar(select(PaymentTransaction)) is None


def test_reused_click_transaction_with_different_order_conflicts(client, db_session):
    settings = click_settings(client)
    first_order, _ = order(client, db_session)
    second_order, _ = order(client, db_session)

    first = prepare(client, first_order, settings, transaction_id="106")
    conflicting = prepare(client, second_order, settings, transaction_id="106")

    assert first.json()["error"] == 0
    assert conflicting.json()["error"] == -2
    assert len(db_session.scalars(select(PaymentTransaction)).all()) == 1


def test_complete_rejects_unknown_prepare_without_changingorder(client, db_session):
    settings = click_settings(client)
    order_id, product_id = order(client, db_session)
    fields = {
        "click_trans_id": "107",
        "service_id": "service",
        "click_user_id": "click-user",
        "merchant_trans_id": str(order_id),
        "merchant_prepare_id": "999999",
        "amount": "12000.00",
        "action": "1",
        "error": "0",
        "error_note": "",
        "click_paydoc_id": "9002",
        "sign_time": "2026-09-28 12:31:00",
    }
    fields["sign_string"] = complete_signature(fields, settings.click_secret_key)

    response = client.post("/payments/click/callback", data=fields)

    assert response.status_code == 200
    assert response.json()["error"] == -6
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "pending"
    assert db_session.get(Product, product_id).stock == 3
    assert db_session.scalar(select(PaymentTransaction)) is None


def test_oversized_transaction_identifier_returns_json_error_not_server_error(client, db_session):
    settings = click_settings(client)
    order_id, _ = order(client, db_session)
    fields = {
        "click_trans_id": "9" * 5000,
        "service_id": settings.click_service_id,
        "click_user_id": "click-user",
        "merchant_trans_id": str(order_id),
        "amount": "12000.00",
        "action": "0",
        "sign_time": "2026-09-28 12:30:00",
    }
    fields["sign_string"] = prepare_signature(fields, settings.click_secret_key)

    response = client.post("/payments/click/callback", data=fields)

    assert response.status_code == 200
    assert response.json()["error"] == -5
    assert response.json()["click_trans_id"] == 0
    assert db_session.scalar(select(PaymentTransaction)) is None


def test_malformed_form_returns_click_json_error(client):
    response = client.post(
        "/payments/click/callback",
        content=b"broken",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "click_trans_id": 0,
        "merchant_trans_id": "",
        "merchant_prepare_id": 0,
        "error": -1,
        "error_note": "Invalid Click request",
    }


def test_negative_click_error_cancels_order_and_releases_reserved_stock(client, db_session):
    settings = click_settings(client)
    order_id, product_id = order(client, db_session)
    prepared = prepare(client, order_id, settings)

    failed = complete(
        client,
        order_id,
        settings,
        prepared.json()["merchant_prepare_id"],
        error="-1",
        paydoc_id="0",
    )
    retry = complete(client, order_id, settings, prepared.json()["merchant_prepare_id"], error="-1")

    assert failed.json()["error"] == -9
    assert retry.json()["error"] == -9
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "cancelled"
    assert db_session.get(Product, product_id).stock == 4
