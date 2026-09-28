from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.products.cache import ProductCache
from app.products.models import Product
from app.products.schemas import ProductPage

router = APIRouter()


@router.get("/products", response_model=ProductPage)
def list_products(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    cache = ProductCache(request.app.state.redis)
    cached = cache.get(page, page_size)
    if cached is not None:
        return cached
    total = session.scalar(select(func.count()).select_from(Product)) or 0
    rows = session.scalars(
        select(Product).order_by(Product.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    payload = ProductPage(items=rows, total=total, page=page, page_size=page_size).model_dump(
        mode="json"
    )
    cache.set(page, page_size, payload)
    return payload
