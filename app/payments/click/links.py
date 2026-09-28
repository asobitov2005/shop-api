from decimal import Decimal
from urllib.parse import urlencode

from app.core.config import Settings


def payment_link(order_id: int, amount: Decimal, settings: Settings) -> str | None:
    """Build Click's browser checkout URL when credentials are configured."""
    if not settings.click_merchant_id:
        return None

    parameters = {
        "merchant_id": settings.click_merchant_id,
        "service_id": settings.click_service_id,
        "amount": format(amount, ".2f"),
        "transaction_param": str(order_id),
    }
    if settings.click_return_url:
        parameters["return_url"] = settings.click_return_url
    return f"https://my.click.uz/services/pay?{urlencode(parameters)}"
