from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.payments.click.form import parse_click_form
from app.payments.click.handlers import process_complete, process_prepare
from app.payments.click.schemas import (
    CompleteFields,
    CompleteResponse,
    PrepareFields,
    PrepareResponse,
)
from app.products.cache import ProductCache

router = APIRouter(prefix="/payments/click")


def _integer(value: str | None) -> int:
    if not value or len(value) > 19 or not value.isdecimal():
        return 0
    try:
        result = int(value)
    except ValueError:
        return 0
    return result if result <= 9_223_372_036_854_775_807 else 0


def _prepare_error(fields: dict[str, str]) -> PrepareResponse:
    return PrepareResponse(
        click_trans_id=_integer(fields.get("click_trans_id")),
        merchant_trans_id=fields.get("merchant_trans_id", ""),
        merchant_prepare_id=0,
        error=-1,
        error_note="Invalid Click request",
    )


def _complete_error(fields: dict[str, str]) -> CompleteResponse:
    return CompleteResponse(
        click_trans_id=_integer(fields.get("click_trans_id")),
        merchant_trans_id=fields.get("merchant_trans_id", ""),
        merchant_confirm_id=0,
        error=-1,
        error_note="Invalid Click request",
    )


async def _fields(request: Request) -> dict[str, str]:
    return parse_click_form(await request.body())


@router.post("/prepare", response_model=PrepareResponse)
async def prepare(
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008
) -> PrepareResponse:
    fields: dict[str, str] = {}
    try:
        fields = await _fields(request)
        payload = PrepareFields.model_validate(fields)
    except (ValueError, ValidationError):
        return _prepare_error(fields)
    cache = ProductCache(request.app.state.redis)
    return process_prepare(session, payload, request.app.state.settings, cache)


@router.post("/complete", response_model=CompleteResponse)
async def complete(
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008
) -> CompleteResponse:
    fields: dict[str, str] = {}
    try:
        fields = await _fields(request)
        payload = CompleteFields.model_validate(fields)
    except (ValueError, ValidationError):
        return _complete_error(fields)
    cache = ProductCache(request.app.state.redis)
    return process_complete(session, payload, request.app.state.settings, cache)
