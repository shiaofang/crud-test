"""商品 CRUD 工具。"""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .. import crud, models, schemas
from ..kafka_bus import emit_product_activity
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


class CreateProductsArgs(BaseModel):
    products: list[CreateProductArgs] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="要创建的商品列表；每项名称必填且互不重复，描述/价格/库存可自填合理值",
    )


class UpdateProductArgs(BaseModel):
    product_id: int = Field(..., ge=1, description="商品 ID")
    name: str | None = Field(None, min_length=1, max_length=100, description="新名称")
    description: str | None = Field(None, max_length=500, description="新描述")
    price: float | None = Field(None, ge=0, description="新价格")
    stock: int | None = Field(None, ge=0, description="新库存")


class UpdateProductsArgs(BaseModel):
    updates: list[UpdateProductArgs] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="要更新的商品列表；每项仅传需要修改的字段，不要传 null",
    )


class DeleteProductArgs(BaseModel):
    product_id: int = Field(..., ge=1, description="商品 ID")


def _create_one_product(
    *,
    name: str,
    description: str | None = None,
    price: float = 0,
    stock: int = 0,
) -> dict[str, Any]:
    """创建单个商品，返回统一结构（供单条/批量工具复用）。"""
    db = _require_db()
    try:
        product = crud.create_product(
            db,
            schemas.ProductCreate(
                name=name, description=description, price=price, stock=stock
            ),
        )
    except ValueError as exc:
        return {"ok": False, "name": name, "error": str(exc)}
    except Exception as exc:
        db.rollback()
        return {"ok": False, "name": name, "error": f"创建失败：{exc}"}

    emit_product_activity(
        action="created",
        product_id=product.id,
        product_name=product.name,
        source="ai",
    )
    return {"ok": True, "product": _product_dict(product)}


def _collect_product_update(
    product: models.Product,
    *,
    name: str | None,
    description: str | None,
    price: float | None,
    stock: int | None,
) -> tuple[dict[str, Any], dict[str, Any]] | str:
    """组装增量字段与变更摘要；无有效字段时返回错误文案。"""
    data: dict[str, Any] = {}
    changes: dict[str, Any] = {}
    if name is not None:
        data["name"] = name
        if name != product.name:
            changes["name"] = (product.name, name)
    if description is not None:
        data["description"] = description
        if description != product.description:
            changes["description"] = True
    if price is not None:
        data["price"] = price
        if float(price) != float(product.price):
            changes["price"] = (float(product.price), float(price))
    if stock is not None:
        data["stock"] = stock
        if stock != product.stock:
            changes["stock"] = (product.stock, stock)
    if not data:
        return "未提供任何要更新的字段"
    return data, changes


def _update_one_product(
    product_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    price: float | None = None,
    stock: int | None = None,
) -> dict[str, Any]:
    """更新单个商品，返回统一结构（供单条/批量工具复用）。"""
    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return {"ok": False, "product_id": product_id, "error": "商品不存在"}

    collected = _collect_product_update(
        product, name=name, description=description, price=price, stock=stock
    )
    if isinstance(collected, str):
        return {"ok": False, "product_id": product_id, "error": collected}
    data, changes = collected

    try:
        updated = crud.update_product(db, product, schemas.ProductUpdate(**data))
    except ValueError as exc:
        return {"ok": False, "product_id": product_id, "error": str(exc)}
    except Exception as exc:
        db.rollback()
        return {"ok": False, "product_id": product_id, "error": f"更新失败：{exc}"}

    emit_product_activity(
        action="updated",
        product_id=updated.id,
        product_name=updated.name,
        source="ai",
        changes=changes or None,
    )
    return {"ok": True, "product": _product_dict(updated)}


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
    """创建单个新商品。名称必填；描述、价格、库存可选。要创建多个时请用 create_products。"""
    result = _create_one_product(
        name=name, description=description, price=price, stock=stock
    )
    if not result.get("ok"):
        return _json({"error": result.get("error", "创建失败")})
    return _json({"ok": True, "product": result["product"]})


@tool("create_products", args_schema=CreateProductsArgs)
@with_tool_session
def create_products(products: list[CreateProductArgs] | list[dict[str, Any]]) -> str:
    """一次批量创建多个商品。每项名称必填且互不相同，描述/价格/库存缺省时可自填合理值。

    用户要创建 2 个及以上商品时必须用本工具，且 products 必须包含全部目标（一条都不许漏），
    不要多次调用 create_product。
    """
    if not products:
        return _json({"error": "products 不能为空"})

    results: list[dict[str, Any]] = []
    for item in products:
        if isinstance(item, CreateProductArgs):
            payload = item
        elif isinstance(item, dict):
            try:
                payload = CreateProductArgs.model_validate(item)
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "name": item.get("name"),
                        "error": f"参数无效：{exc}",
                    }
                )
                continue
        else:
            results.append({"ok": False, "error": "参数无效"})
            continue

        results.append(
            _create_one_product(
                name=payload.name,
                description=payload.description,
                price=payload.price,
                stock=payload.stock,
            )
        )

    success_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - success_count
    created_ids = [
        r["product"]["id"] for r in results if r.get("ok") and r.get("product")
    ]
    created_names = [
        r["product"]["name"] for r in results if r.get("ok") and r.get("product")
    ]
    failed = [
        {"name": r.get("name"), "error": r.get("error")}
        for r in results
        if not r.get("ok")
    ]
    return _json(
        {
            "ok": success_count > 0,
            "requested_count": len(results),
            "success_count": success_count,
            "fail_count": fail_count,
            "created_ids": created_ids,
            "created_names": created_names,
            "failed": failed,
            "results": results,
        }
    )


@tool("update_product", args_schema=UpdateProductArgs)
@with_tool_session
def update_product(
    product_id: int,
    name: str | None = None,
    description: str | None = None,
    price: float | None = None,
    stock: int | None = None,
) -> str:
    """按 ID 更新单个商品字段（仅传需要修改的字段，不要传 null）。要改多个商品时请用 update_products。"""
    result = _update_one_product(
        product_id, name=name, description=description, price=price, stock=stock
    )
    if not result.get("ok"):
        return _json({"error": result.get("error", "更新失败")})
    return _json({"ok": True, "product": result["product"]})


@tool("update_products", args_schema=UpdateProductsArgs)
@with_tool_session
def update_products(updates: list[UpdateProductArgs] | list[dict[str, Any]]) -> str:
    """一次批量更新多个商品。每项可改不同字段（名称/描述/价格/库存），仅传需要修改的字段。

    用户要改 2 个及以上商品时必须用本工具，且 updates 必须包含全部目标（一条都不许漏），
    不要多次调用 update_product，也不要分批漏改。
    """
    if not updates:
        return _json({"error": "updates 不能为空"})

    results: list[dict[str, Any]] = []
    for item in updates:
        if isinstance(item, UpdateProductArgs):
            payload = item
        elif isinstance(item, dict):
            try:
                payload = UpdateProductArgs.model_validate(item)
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "product_id": item.get("product_id"),
                        "error": f"参数无效：{exc}",
                    }
                )
                continue
        else:
            results.append({"ok": False, "error": "参数无效"})
            continue

        results.append(
            _update_one_product(
                payload.product_id,
                name=payload.name,
                description=payload.description,
                price=payload.price,
                stock=payload.stock,
            )
        )

    success_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - success_count
    updated_ids = [
        r["product"]["id"] for r in results if r.get("ok") and r.get("product")
    ]
    updated_names = [
        r["product"]["name"] for r in results if r.get("ok") and r.get("product")
    ]
    failed = [
        {"product_id": r.get("product_id"), "error": r.get("error")}
        for r in results
        if not r.get("ok")
    ]
    return _json(
        {
            "ok": success_count > 0,
            "requested_count": len(results),
            "success_count": success_count,
            "fail_count": fail_count,
            "updated_ids": updated_ids,
            "updated_names": updated_names,
            "failed": failed,
            "results": results,
        }
    )


@tool("delete_product", args_schema=DeleteProductArgs)
@with_tool_session
def delete_product(product_id: int) -> str:
    """按 ID 删除商品。"""
    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})

    name = product.name
    crud.delete_product(db, product)
    emit_product_activity(
        action="deleted",
        product_id=product_id,
        product_name=name,
        source="ai",
    )
    return _json({"ok": True, "deleted_id": product_id})


PRODUCT_TOOLS: list[BaseTool] = [
    list_products,
    get_product,
    create_product,
    create_products,
    update_product,
    update_products,
    delete_product,
]
