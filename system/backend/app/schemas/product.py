from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.schemas.common import Pagination

ProductType = Literal["INTERNAL", "COMPETITOR"]
PriceType = Literal["GUIDE", "SALES", "INTERNAL_QUOTE"]


class ProductCreateRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=80)
    category: str | None = Field(default=None, max_length=80)
    brand: str = Field(min_length=1, max_length=80)
    product_type: ProductType = "INTERNAL"
    description: str | None = None


class ProductUpdateRequest(ProductCreateRequest):
    pass


class ProductData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_name: str
    model: str
    category: str | None
    brand: str
    product_type: ProductType
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProductListData(BaseModel):
    items: list[ProductData]
    pagination: Pagination


class ProductOptionsData(BaseModel):
    brands: list[str]
    categories: list[str]


class BulkProductDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)


class PriceProductData(BaseModel):
    id: int
    product_name: str
    model: str


class PriceData(BaseModel):
    quote_spec: str | None = None
    pricing_unit: str | None = None
    included_scope: str | None = None

    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    price: Decimal
    currency: str
    price_type: PriceType
    source: str
    update_time: datetime

    @field_serializer("price")
    def serialize_price(self, value: Decimal) -> str:
        return f"{value:.2f}"


class ProductPricesData(BaseModel):
    product: PriceProductData
    prices: list[PriceData]
