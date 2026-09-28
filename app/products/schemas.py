from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProductView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: Decimal
    currency: Literal["UZS"]
    stock: int


class ProductPage(BaseModel):
    items: list[ProductView]
    total: int
    page: int
    page_size: int
