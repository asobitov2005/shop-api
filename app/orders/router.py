from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.orders.schemas import OrderCreate, OrderView
from app.orders.service import create_order
from app.payments.click.links import payment_link
from app.products.cache import ProductCache

router = APIRouter()


@router.post("/orders", response_model=OrderView, status_code=status.HTTP_201_CREATED)
def post_order(
    payload: OrderCreate,
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008
) -> OrderView:
    order = create_order(session, payload, ProductCache(request.app.state.redis))
    settings = request.app.state.settings
    return OrderView(
        id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        currency=order.currency,
        expires_at=order.expires_at,
        payment_url=payment_link(order.id, order.total_amount, settings),
    )
