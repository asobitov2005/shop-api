import hashlib
import hmac
import re

_SIGNATURE = re.compile(r"[0-9a-f]{64}\Z")


def verify_task_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if signature is None or _SIGNATURE.fullmatch(signature) is None:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
