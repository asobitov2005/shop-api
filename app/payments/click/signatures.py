import hashlib
from collections.abc import Mapping


def prepare_signature(fields: Mapping[str, str], secret: str) -> str:
    signed = "".join(
        (
            fields["click_trans_id"],
            fields["service_id"],
            secret,
            fields["merchant_trans_id"],
            fields["amount"],
            fields["action"],
            fields["sign_time"],
        )
    )
    return hashlib.md5(signed.encode()).hexdigest()


def complete_signature(fields: Mapping[str, str], secret: str) -> str:
    signed = "".join(
        (
            fields["click_trans_id"],
            fields["service_id"],
            secret,
            fields["merchant_trans_id"],
            fields["merchant_prepare_id"],
            fields["amount"],
            fields["action"],
            fields["sign_time"],
        )
    )
    return hashlib.md5(signed.encode()).hexdigest()
