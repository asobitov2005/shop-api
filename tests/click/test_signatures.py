import hashlib

from app.payments.click.signatures import complete_signature, prepare_signature


def test_prepare_signature_uses_original_field_strings():
    fields = {
        "click_trans_id": "00019",
        "service_id": "002",
        "merchant_trans_id": "order-8",
        "amount": "010.00",
        "action": "0",
        "sign_time": "2026-09-28 12:30:00",
    }

    expected = hashlib.md5(b"00019002secretorder-8010.0002026-09-28 12:30:00").hexdigest()

    assert prepare_signature(fields, "secret") == expected


def test_complete_signature_includes_prepare_id_before_amount():
    fields = {
        "click_trans_id": "19",
        "service_id": "2",
        "merchant_trans_id": "8",
        "merchant_prepare_id": "42",
        "amount": "10.00",
        "action": "1",
        "sign_time": "2026-09-28 12:30:00",
    }
    expected = hashlib.md5(b"192secret84210.0012026-09-28 12:30:00").hexdigest()

    assert complete_signature(fields, "secret") == expected
