import pytest

from app.payments.click.form import parse_click_form


def test_form_parser_preserves_amount_strings_and_decodes_values():
    body = b"amount=0010.00&merchant_trans_id=order%2F7&sign_time=2026-09-28"

    assert parse_click_form(body) == {
        "amount": "0010.00",
        "merchant_trans_id": "order/7",
        "sign_time": "2026-09-28",
    }


@pytest.mark.parametrize("body", [b"", b"amount=1&amount=2", b"amount=%FF", b"broken"])
def test_form_parser_rejects_ambiguous_or_malformed_fields(body):
    with pytest.raises(ValueError):
        parse_click_form(body)
