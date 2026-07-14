"""智能助手可用的数据库工具（商品 + 用户）。"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import crud, models, schemas, security
from .database import SessionLocal

_db_var: ContextVar[Session | None] = ContextVar("tool_db", default=None)
_user_var: ContextVar[models.User | None] = ContextVar("tool_user", default=None)
_mutations_var: ContextVar[set[str] | None] = ContextVar("tool_mutations", default=None)

LOGIN_REQUIRED_MSG = "未登录：请先登录后再进行数据库操作"


def set_tool_context(db: Session, current_user: models.User | None) -> tuple[Any, Any, Any]:
    """绑定本轮请求的 db / 登录用户 / 变更集合，返回 token 供重置。"""
    return _db_var.set(db), _user_var.set(current_user), _mutations_var.set(set())


def reset_tool_context(db_token: Any, user_token: Any, mutations_token: Any) -> None:
    _db_var.reset(db_token)
    _user_var.reset(user_token)
    _mutations_var.reset(mutations_token)


def get_mutations() -> list[str]:
    """返回本轮成功写入过的资源名，如 products / users。"""
    mutations = _mutations_var.get()
    return sorted(mutations) if mutations else []


def rollback_tool_db() -> None:
    """工具执行失败后回滚当前 Session，避免后续调用继续报错。"""
    db = _db_var.get()
    if db is not None:
        try:
            db.rollback()
        except Exception:
            pass


def run_with_tool_session(fn: Callable[[], str]) -> str:
    """在当前线程用短生命周期 Session 执行 fn，并与父上下文共享 mutations。

    供 asyncio.to_thread 调用：避免阻塞事件循环，且不跨线程复用请求级 Session。
    """
    user = _user_var.get()
    mutations = _mutations_var.get()
    if mutations is None:
        mutations = set()

    db = SessionLocal()
    db_token = _db_var.set(db)
    user_token = _user_var.set(user)
    mut_token = _mutations_var.set(mutations)
    try:
        return fn()
    finally:
        try:
            db.close()
        except Exception:
            pass
        _db_var.reset(db_token)
        _user_var.reset(user_token)
        _mutations_var.reset(mut_token)


def _mark_mutation(resource: str) -> None:
    mutations = _mutations_var.get()
    if mutations is not None:
        mutations.add(resource)


def _require_db() -> Session:
    db = _db_var.get()
    if db is None:
        raise RuntimeError("工具上下文未初始化")
    return db


def _require_login() -> models.User | str:
    user = _user_var.get()
    if user is None:
        return LOGIN_REQUIRED_MSG
    return user


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _product_dict(p: models.Product) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "price": float(p.price),
        "stock": p.stock,
        "clickCount": p.clickCount,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _user_dict(u: models.User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "created_at": u.created_at,
    }


# ---- Hot products (public) ----


class ListHotProductsArgs(BaseModel):
    keyword: str | None = Field(None, description="按商品名称模糊搜索")
    limit: int = Field(3, ge=1, le=20, description="返回数量，默认 3")


def _list_hot_products(keyword: str | None = None, limit: int = 3) -> str:
    """按点击量查询热门商品，无需登录。"""
    db = _require_db()
    items = crud.get_hot_products(db, limit=limit, keyword=keyword)
    return _json({"total": len(items), "items": [_product_dict(p) for p in items]})


# ---- Product tools ----


class ListProductsArgs(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(10, ge=1, le=50, description="每页数量")
    keyword: str | None = Field(None, description="按商品名称模糊搜索")


def _list_products(page: int = 1, page_size: int = 10, keyword: str | None = None) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    skip = (page - 1) * page_size
    total, items = crud.get_products(db, skip=skip, limit=page_size, keyword=keyword)
    return _json({"total": total, "items": [_product_dict(p) for p in items]})


class GetProductArgs(BaseModel):
    product_id: int = Field(..., ge=1, description="商品 ID")


def _get_product(product_id: int) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})
    return _json(_product_dict(product))


class CreateProductArgs(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="商品名称")
    description: str | None = Field(None, max_length=500, description="描述")
    price: float = Field(0, ge=0, description="价格")
    stock: int = Field(0, ge=0, description="库存")


def _create_product(
    name: str,
    description: str | None = None,
    price: float = 0,
    stock: int = 0,
) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    try:
        product = crud.create_product(
            db,
            schemas.ProductCreate(name=name, description=description, price=price, stock=stock),
        )
    except ValueError as exc:
        return _json({"error": str(exc)})
    except Exception as exc:
        db.rollback()
        return _json({"error": f"创建失败：{exc}"})
    _mark_mutation("products")
    return _json({"ok": True, "product": _product_dict(product)})


class UpdateProductArgs(BaseModel):
    product_id: int = Field(..., ge=1, description="商品 ID")
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    price: float | None = Field(None, ge=0)
    stock: int | None = Field(None, ge=0)


def _update_product(
    product_id: int,
    name: str | None = None,
    description: str | None = None,
    price: float | None = None,
    stock: int | None = None,
) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})
    # 只带上真正要改的字段，避免把未传字段写成 null
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
    _mark_mutation("products")
    return _json({"ok": True, "product": _product_dict(updated)})


class DeleteProductArgs(BaseModel):
    product_id: int = Field(..., ge=1, description="商品 ID")


def _delete_product(product_id: int) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})
    crud.delete_product(db, product)
    _mark_mutation("products")
    return _json({"ok": True, "deleted_id": product_id})


# ---- User tools ----


class ListUsersArgs(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(10, ge=1, le=50, description="每页数量")
    keyword: str | None = Field(None, description="按用户名模糊搜索")


def _list_users(page: int = 1, page_size: int = 10, keyword: str | None = None) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    skip = (page - 1) * page_size
    total, items = crud.list_users(db, skip=skip, limit=page_size, keyword=keyword)
    return _json({"total": total, "items": [_user_dict(u) for u in items]})


class GetUserArgs(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")


def _get_user(user_id: int) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    user = crud.get_user(db, user_id)
    if user is None:
        return _json({"error": "用户不存在"})
    return _json(_user_dict(user))


class CreateUserArgs(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    email: str | None = Field(None, description="邮箱")


def _create_user(username: str, password: str, email: str | None = None) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    if crud.get_user_by_username(db, username):
        return _json({"error": "用户名已存在"})
    if email and crud.get_user_by_email(db, email):
        return _json({"error": "邮箱已被使用"})
    try:
        payload = schemas.UserRegister(username=username, password=password, email=email)
    except Exception as exc:
        return _json({"error": f"参数无效：{exc}"})
    user = crud.create_user(db, payload, security.hash_password(password))
    _mark_mutation("users")
    return _json({"ok": True, "user": _user_dict(user)})


class UpdateUserArgs(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    username: str | None = Field(None, min_length=3, max_length=50)
    email: str | None = Field(None, description="邮箱")
    password: str | None = Field(None, min_length=6, max_length=128, description="新密码")


def _update_user(
    user_id: int,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> str:
    if isinstance(_require_login(), str):
        return LOGIN_REQUIRED_MSG
    db = _require_db()
    user = crud.get_user(db, user_id)
    if user is None:
        return _json({"error": "用户不存在"})
    if username and username != user.username and crud.get_user_by_username(db, username):
        return _json({"error": "用户名已存在"})
    if email and email != user.email and crud.get_user_by_email(db, email):
        return _json({"error": "邮箱已被使用"})
    hashed = security.hash_password(password) if password else None
    updated = crud.update_user(
        db,
        user,
        username=username,
        email=email,
        hashed_password=hashed,
    )
    _mark_mutation("users")
    return _json({"ok": True, "user": _user_dict(updated)})


class DeleteUserArgs(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")


def _delete_user(user_id: int) -> str:
    current = _require_login()
    if isinstance(current, str):
        return LOGIN_REQUIRED_MSG
    if current.id == user_id:
        return _json({"error": "不能删除当前登录用户自己"})
    db = _require_db()
    user = crud.get_user(db, user_id)
    if user is None:
        return _json({"error": "用户不存在"})
    crud.delete_user(db, user)
    _mark_mutation("users")
    return _json({"ok": True, "deleted_id": user_id})


def build_tools() -> list[BaseTool]:
    """构造本应用全部助手工具。"""
    return [
        StructuredTool.from_function(
            func=_list_hot_products,
            name="list_hot_products",
            description="查询热门商品（按点击量排序）。公开接口，无需登录。",
            args_schema=ListHotProductsArgs,
        ),
        StructuredTool.from_function(
            func=_list_products,
            name="list_products",
            description="分页查询商品列表，可按名称关键字搜索。",
            args_schema=ListProductsArgs,
        ),
        StructuredTool.from_function(
            func=_get_product,
            name="get_product",
            description="按 ID 查询单个商品详情。",
            args_schema=GetProductArgs,
        ),
        StructuredTool.from_function(
            func=_create_product,
            name="create_product",
            description="创建新商品（名称、描述、价格、库存）。商品名称不可与已有商品重复。",
            args_schema=CreateProductArgs,
        ),
        StructuredTool.from_function(
            func=_update_product,
            name="update_product",
            description="按 ID 更新商品字段（仅传需要修改的字段，不要传 null）。",
            args_schema=UpdateProductArgs,
        ),
        StructuredTool.from_function(
            func=_delete_product,
            name="delete_product",
            description="按 ID 删除商品。",
            args_schema=DeleteProductArgs,
        ),
        StructuredTool.from_function(
            func=_list_users,
            name="list_users",
            description="分页查询用户列表，可按用户名关键字搜索。",
            args_schema=ListUsersArgs,
        ),
        StructuredTool.from_function(
            func=_get_user,
            name="get_user",
            description="按 ID 查询单个用户（不含密码）。",
            args_schema=GetUserArgs,
        ),
        StructuredTool.from_function(
            func=_create_user,
            name="create_user",
            description="创建新用户（用户名、密码、可选邮箱）。",
            args_schema=CreateUserArgs,
        ),
        StructuredTool.from_function(
            func=_update_user,
            name="update_user",
            description="按 ID 更新用户（用户名、邮箱、密码均可选）。",
            args_schema=UpdateUserArgs,
        ),
        StructuredTool.from_function(
            func=_delete_user,
            name="delete_user",
            description="按 ID 删除用户（不能删除当前登录用户自己）。",
            args_schema=DeleteUserArgs,
        ),
    ]
