"""商品 CRUD 工具。"""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .. import crud, schemas
from ._make import _DEFAULT_PAGE_SIZE, _PaginationArgs, _clamp_page_size
from .context import _require_db, with_tool_session
from .serialize import _json, _product_dict, _product_summary_dict


class ListProductsArgs(_PaginationArgs):
    keyword: str | None = Field(None, description="按商品名称模糊搜索")


class GetProductArgs(BaseModel):
    product_id: int = Field(..., ge=1, description="商品 ID")


class CreateProductArgs(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="商品名称（必填）")
    description: str | None = Field(
        None, max_length=500, description="描述；用户未提供时可自行填写合理内容"
    )
    price: float = Field(0, ge=0, description="价格；用户未提供时可自行填写合理正数")
    stock: int = Field(0, ge=0, description="库存；用户未提供时可自行填写合理非负整数")


class UpdateProductArgs(BaseModel):
    product_id: int = Field(..., ge=1, description="商品 ID")
    name: str | None = Field(None, min_length=1, max_length=100, description="新名称")
    description: str | None = Field(None, max_length=500, description="新描述")
    price: float | None = Field(None, ge=0, description="新价格")
    stock: int | None = Field(None, ge=0, description="新库存")


class DeleteProductArgs(BaseModel):
    product_id: int = Field(..., ge=1, description="商品 ID")


@tool("list_products", args_schema=ListProductsArgs)
@with_tool_session
def list_products(
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    keyword: str | None = None,
) -> str:
    """分页查询商品列表，可按名称关键字搜索。"""
    db = _require_db()
    page_size = _clamp_page_size(page_size)
    skip = (page - 1) * page_size
    total, items = crud.get_products(db, skip=skip, limit=page_size, keyword=keyword)
    return _json(
        {
            "total": total,
            "items": [_product_summary_dict(p) for p in items],
        }
    )


@tool("get_product", args_schema=GetProductArgs)
@with_tool_session
def get_product(product_id: int) -> str:
    """按 ID 查询单个商品详情。"""
    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})
    return _json(_product_dict(product))


@tool("create_product", args_schema=CreateProductArgs)
@with_tool_session
def create_product(
    name: str,
    description: str | None = None,
    price: float = 0,
    stock: int = 0,
) -> str:
    """创建新商品。名称必填；描述、价格、库存可选，缺省时可传合理示例值。商品名称不可与已有商品重复。"""
    db = _require_db()
    try:
        product = crud.create_product(
            db,
            schemas.ProductCreate(
                name=name, description=description, price=price, stock=stock
            ),
        )
    except ValueError as exc:
        return _json({"error": str(exc)})
    except Exception as exc:
        db.rollback()
        return _json({"error": f"创建失败：{exc}"})

    return _json({"ok": True, "product": _product_dict(product)})


@tool("update_product", args_schema=UpdateProductArgs)
@with_tool_session
def update_product(
    product_id: int,
    name: str | None = None,
    description: str | None = None,
    price: float | None = None,
    stock: int | None = None,
) -> str:
    """按 ID 更新单个商品字段（仅传需要修改的字段，不要传 null）。一次要改多个商品时，请在同一轮并行多次调用本工具。"""
    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})

    data: dict[str, Any] = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if price is not None:
        data["price"] = price
    if stock is not None:
        data["stock"] = stock
    if not data:
        return _json({"error": "未提供任何要更新的字段"})

    try:
        updated = crud.update_product(db, product, schemas.ProductUpdate(**data))
    except ValueError as exc:
        return _json({"error": str(exc)})
    except Exception as exc:
        db.rollback()
        return _json({"error": f"更新失败：{exc}"})

    return _json({"ok": True, "product": _product_dict(updated)})


@tool("delete_product", args_schema=DeleteProductArgs)
@with_tool_session
def delete_product(product_id: int) -> str:
    """按 ID 删除商品。"""
    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})

    crud.delete_product(db, product)
    return _json({"ok": True, "deleted_id": product_id})


PRODUCT_TOOLS: list[BaseTool] = [
    list_products,
    get_product,
    create_product,
    update_product,
    delete_product,
]
