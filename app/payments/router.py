import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.payments.schemas import CallbackResult, TaskCallback
from app.payments.service import process_task_callback
from app.payments.signatures import verify_task_signature
from app.products.cache import ProductCache

router = APIRouter(prefix="/payments")


def _parse_callback(raw_body: bytes) -> TaskCallback:
    try:
        payload = json.loads(raw_body, parse_float=Decimal, parse_int=int)
        return TaskCallback.model_validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError) as error:
        raise HTTPException(status_code=422, detail="Invalid callback payload") from error


@router.post("/callback", response_model=CallbackResult)
async def task_callback(
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008
    x_signature: str | None = Header(default=None),
) -> CallbackResult:
    raw_body = await request.body()
    settings = request.app.state.settings
    if not verify_task_signature(raw_body, x_signature, settings.task_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = _parse_callback(raw_body)
    result = process_task_callback(session, payload, ProductCache(request.app.state.redis))
    return CallbackResult(**result.__dict__)
