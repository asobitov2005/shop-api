from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field


class ProductView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: Decimal
    discount_amount: Decimal
    currency: Literal["UZS"]
    stock: int

    @computed_field
    @property
    def original_price(self) -> Decimal:
        return self.price + self.discount_amount


class ProductPage(BaseModel):
    items: list[ProductView]
    total: int
    page: int
    page_size: int
