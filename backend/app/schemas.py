from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="商品名称")
    description: str | None = Field(None, max_length=500, description="描述")
    price: float = Field(0, ge=0, description="价格")
    stock: int = Field(0, ge=0, description="库存")


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    price: float | None = Field(None, ge=0)
    stock: int | None = Field(None, ge=0)


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    total: int
    items: list[ProductOut]
