from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class TaskCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: Annotated[str, Field(min_length=1, max_length=200)]
    order_id: Annotated[StrictInt, Field(gt=0)]
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
    status: Literal["success", "failed"]

    @field_validator("transaction_id")
    @classmethod
    def transaction_id_not_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("transaction_id must not be blank")
        return value


class CallbackResult(BaseModel):
    transaction_id: str
    order_id: int
    status: str
