from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ProductView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: Decimal
    stock: int


class ProductPage(BaseModel):
    items: list[ProductView]
    total: int
    page: int
    page_size: int
