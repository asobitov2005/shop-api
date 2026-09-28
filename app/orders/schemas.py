from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class OrderItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: Annotated[StrictInt, Field(gt=0)]
    quantity: Annotated[StrictInt, Field(gt=0)]


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[OrderItemInput], Field(min_length=1)]


class OrderView(BaseModel):
    id: int
    status: str
    total_amount: Decimal
    currency: Literal["UZS"]
    expires_at: datetime
    payment_url: None = None
