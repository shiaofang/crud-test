"""智能助手可用的数据库工具（商品 + 用户）。

本模块向 LangChain Agent 暴露可调用的 StructuredTool，覆盖：
- 商品 / 用户的分页列表、详情、创建、更新、删除（需登录）

设计要点：
- 通过 ContextVar 绑定「本轮请求」的 Session、登录用户与变更集合，
  避免把 db/user 塞进工具参数（模型不可见、也不可靠）。
- 工具在 asyncio.to_thread 中执行时使用短生命周期 Session
  （见 run_with_tool_session），避免阻塞事件循环与跨线程复用 Session。
- 写操作成功后通过 _mark_mutation 记录资源名，供前端按需刷新列表。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextvars import ContextVar, Token
from datetime import datetime
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from . import crud, models, schemas, security
from .database import SessionLocal

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

LOGIN_REQUIRED_MSG = "未登录：请先登录后再进行数据库操作"

# 分页：默认每页条数 / 单页上限
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100

# ---------------------------------------------------------------------------
# 请求级上下文（ContextVar）
# ---------------------------------------------------------------------------

_db_var: ContextVar[Session | None] = ContextVar("tool_db", default=None)
_user_var: ContextVar[models.User | None] = ContextVar("tool_user", default=None)
_mutations_var: ContextVar[set[str] | None] = ContextVar("tool_mutations", default=None)

# set_tool_context / reset_tool_context 使用的 token 三元组
ToolContextTokens = tuple[Token, Token, Token]


# ---------------------------------------------------------------------------
# 上下文：对外 API（供 llm.py 等调用方使用）
# ---------------------------------------------------------------------------


def set_tool_context(
    db: Session, current_user: models.User | None
) -> ToolContextTokens:
    """绑定本轮请求的工具执行上下文。

    Args:
        db: 当前请求的 SQLAlchemy Session。
        current_user: 已登录用户；未登录时传 None。

    Returns:
        三个 ContextVar token，须在请求结束时交给 reset_tool_context 还原。
    """
    return (
        _db_var.set(db),
        _user_var.set(current_user),
        _mutations_var.set(set()),
    )


def reset_tool_context(
    db_token: Token, user_token: Token, mutations_token: Token
) -> None:
    """还原 set_tool_context 写入的 ContextVar，避免请求间串扰。

    Args:
        db_token: set_tool_context 返回的 db token。
        user_token: set_tool_context 返回的 user token。
        mutations_token: set_tool_context 返回的 mutations token。
    """
    _db_var.reset(db_token)
    _user_var.reset(user_token)
    _mutations_var.reset(mutations_token)


def get_mutations() -> list[str]:
    """返回本轮成功写入过的资源名（排序后），供前端刷新对应列表。

    Returns:
        例如 ``["products"]``、``["products", "users"]``；无写入时返回空列表。
    """
    mutations = _mutations_var.get()
    return sorted(mutations) if mutations else []


def rollback_tool_db() -> None:
    """工具执行失败后回滚当前 Session，避免脏事务影响后续调用。

    Session 未绑定时静默跳过；rollback 自身异常也会被吞掉，避免掩盖原错误。
    """
    db = _db_var.get()
    if db is None:
        return
    try:
        db.rollback()
    except Exception:
        pass


def run_with_tool_session(fn: Callable[[], str]) -> str:
    """在短生命周期 Session 中执行工具函数，并与父上下文共享 mutations。

    供 ``asyncio.to_thread`` 调用：不阻塞事件循环，且不跨线程复用请求级 Session。
    会继承父上下文中的登录用户与 mutations 集合；执行结束后关闭临时 Session
    并还原本线程内覆盖过的 ContextVar。

    Args:
        fn: 无参可调用对象，返回工具结果的 JSON 字符串。

    Returns:
        ``fn()`` 的返回值。
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


# ---------------------------------------------------------------------------
# 内部辅助：上下文取值 / 登录校验 / 变更标记
# ---------------------------------------------------------------------------


def _mark_mutation(resource: str) -> None:
    """将成功写入的资源名记入本轮 mutations 集合。

    Args:
        resource: 资源标识，如 ``"products"``、``"users"``。
    """
    mutations = _mutations_var.get()
    if mutations is not None:
        mutations.add(resource)


def _require_db() -> Session:
    """获取当前绑定的 Session；未初始化时抛出 RuntimeError。

    Returns:
        当前工具上下文中的 SQLAlchemy Session。

    Raises:
        RuntimeError: 调用方未先执行 set_tool_context / run_with_tool_session。
    """
    db = _db_var.get()
    if db is None:
        raise RuntimeError("工具上下文未初始化")
    return db


def _current_user() -> models.User | None:
    """返回当前登录用户；未登录时返回 None。"""
    return _user_var.get()


def _login_error() -> str | None:
    """未登录时返回固定错误文案，已登录返回 None。

    工具实现中统一写法::

        login_error = _login_error()
        if login_error is not None:
            return login_error
    """
    if _current_user() is None:
        return LOGIN_REQUIRED_MSG
    return None


# ---------------------------------------------------------------------------
# 内部辅助：JSON 序列化与模型字典
# ---------------------------------------------------------------------------


def _json_default(obj: Any) -> Any:
    """json.dumps 的 default 回调：将 datetime 转为 ISO 字符串。

    Args:
        obj: 无法直接序列化的对象。

    Returns:
        可 JSON 序列化的值。

    Raises:
        TypeError: 不支持的类型。
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json(data: Any) -> str:
    """将任意可序列化对象转为 UTF-8 JSON 字符串（保留中文）。

    Args:
        data: 字典、列表等可 JSON 序列化的结构。

    Returns:
        JSON 字符串，供工具返回给大模型。
    """
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _product_dict(product: models.Product) -> dict[str, Any]:
    """商品完整字段字典（详情 / 写操作回显）。

    Args:
        product: ORM 商品实例。

    Returns:
        含 id、名称、描述、价格、库存与时间戳的字典。
    """
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": float(product.price),
        "stock": product.stock,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }


def _product_summary_dict(product: models.Product) -> dict[str, Any]:
    """商品精简字段字典（列表场景，降低多轮上下文体积）。

    Args:
        product: ORM 商品实例。

    Returns:
        仅含 id、name、price、stock 的字典。
    """
    return {
        "id": product.id,
        "name": product.name,
        "price": float(product.price),
        "stock": product.stock,
    }


def _user_dict(user: models.User) -> dict[str, Any]:
    """用户公开字段字典（不含密码）。

    Args:
        user: ORM 用户实例。

    Returns:
        含 id、username、email、created_at 的字典。
    """
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at,
    }


def _user_summary_dict(user: models.User) -> dict[str, Any]:
    """用户精简字段字典（列表场景）。

    Args:
        user: ORM 用户实例。

    Returns:
        仅含 id、username、email 的字典。
    """
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
    }


# ---------------------------------------------------------------------------
# 内部辅助：分页与工具注册
# ---------------------------------------------------------------------------


def _clamp_page_size(
    value: Any,
    *,
    default: int = _DEFAULT_PAGE_SIZE,
    maximum: int = _MAX_PAGE_SIZE,
) -> int:
    """将 page_size 规范到 ``[1, maximum]``；非法值回退为 default。

    Args:
        value: 原始入参（可能是 str / float / None 等）。
        default: 解析失败时的默认值。
        maximum: 允许的最大每页条数。

    Returns:
        合法的每页条数。
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, maximum))


def _make_tool(
    *,
    func: Callable[..., str],
    name: str,
    description: str,
    args_schema: type[BaseModel],
) -> StructuredTool:
    """用统一参数构造 LangChain StructuredTool。

    Args:
        func: 工具实现函数，返回 JSON 字符串。
        name: 暴露给模型的工具名。
        description: 工具用途说明（影响模型是否调用）。
        args_schema: Pydantic 入参模型。

    Returns:
        已注册的 StructuredTool 实例。
    """
    return StructuredTool.from_function(
        func=func,
        name=name,
        description=description,
        args_schema=args_schema,
    )


class _PaginationArgs(BaseModel):
    """分页查询共用入参（页码 + 每页条数）。"""

    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(
        _DEFAULT_PAGE_SIZE,
        ge=1,
        description=f"每页数量，最大 {_MAX_PAGE_SIZE}；超出将自动截断为 {_MAX_PAGE_SIZE}",
    )

    @field_validator("page_size", mode="before")
    @classmethod
    def _validate_page_size(cls, value: Any) -> int:
        return _clamp_page_size(value)


# ===========================================================================
# 商品工具（需登录）
# ===========================================================================


class ListProductsArgs(_PaginationArgs):
    """list_products 入参。"""

    keyword: str | None = Field(None, description="按商品名称模糊搜索")


def _list_products(
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    keyword: str | None = None,
) -> str:
    """分页查询商品列表（精简字段），可按名称关键字搜索。

    Args:
        page: 页码，从 1 开始。
        page_size: 每页条数，最大 100。
        keyword: 可选，按商品名称模糊搜索。

    Returns:
        未登录返回 ``LOGIN_REQUIRED_MSG``；
        否则 JSON：``{"total": int, "items": [精简商品, ...]}``。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

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


class GetProductArgs(BaseModel):
    """get_product 入参。"""

    product_id: int = Field(..., ge=1, description="商品 ID")


def _get_product(product_id: int) -> str:
    """按 ID 查询单个商品详情。

    Args:
        product_id: 商品主键，须 >= 1。

    Returns:
        未登录返回 ``LOGIN_REQUIRED_MSG``；
        不存在返回 ``{"error": "商品不存在"}``；
        成功返回商品完整字段 JSON。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})
    return _json(_product_dict(product))


class CreateProductArgs(BaseModel):
    """create_product 入参。"""

    name: str = Field(..., min_length=1, max_length=100, description="商品名称（必填）")
    description: str | None = Field(
        None, max_length=500, description="描述；用户未提供时可自行填写合理内容"
    )
    price: float = Field(0, ge=0, description="价格；用户未提供时可自行填写合理正数")
    stock: int = Field(0, ge=0, description="库存；用户未提供时可自行填写合理非负整数")


def _create_product(
    name: str,
    description: str | None = None,
    price: float = 0,
    stock: int = 0,
) -> str:
    """创建新商品；名称不可与已有商品重复。

    Args:
        name: 商品名称（必填）。
        description: 可选描述。
        price: 价格，默认 0。
        stock: 库存，默认 0。

    Returns:
        未登录返回 ``LOGIN_REQUIRED_MSG``；
        业务/系统错误返回 ``{"error": "..."}``；
        成功返回 ``{"ok": True, "product": {...}}``，并标记 products 变更。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

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

    _mark_mutation("products")
    return _json({"ok": True, "product": _product_dict(product)})


class UpdateProductArgs(BaseModel):
    """update_product 入参；仅传需要修改的字段。"""

    product_id: int = Field(..., ge=1, description="商品 ID")
    name: str | None = Field(None, min_length=1, max_length=100, description="新名称")
    description: str | None = Field(None, max_length=500, description="新描述")
    price: float | None = Field(None, ge=0, description="新价格")
    stock: int | None = Field(None, ge=0, description="新库存")


def _update_product(
    product_id: int,
    name: str | None = None,
    description: str | None = None,
    price: float | None = None,
    stock: int | None = None,
) -> str:
    """按 ID 部分更新商品；未传字段保持原值，勿传 null 覆盖。

    Args:
        product_id: 商品主键。
        name: 新名称；None 表示不改。
        description: 新描述；None 表示不改。
        price: 新价格；None 表示不改。
        stock: 新库存；None 表示不改。

    Returns:
        未登录 / 不存在 / 无有效字段 / 业务错误时返回对应 error；
        成功返回 ``{"ok": True, "product": {...}}``，并标记 products 变更。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

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
    """delete_product 入参。"""

    product_id: int = Field(..., ge=1, description="商品 ID")


def _delete_product(product_id: int) -> str:
    """按 ID 删除商品。

    Args:
        product_id: 商品主键。

    Returns:
        未登录 / 不存在时返回对应错误；
        成功返回 ``{"ok": True, "deleted_id": id}``，并标记 products 变更。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

    db = _require_db()
    product = crud.get_product(db, product_id)
    if product is None:
        return _json({"error": "商品不存在"})

    crud.delete_product(db, product)
    _mark_mutation("products")
    return _json({"ok": True, "deleted_id": product_id})


# ===========================================================================
# 用户工具（需登录）
# ===========================================================================


class ListUsersArgs(_PaginationArgs):
    """list_users 入参。"""

    keyword: str | None = Field(None, description="按用户名模糊搜索")


def _list_users(
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    keyword: str | None = None,
) -> str:
    """分页查询用户列表（精简字段），可按用户名关键字搜索。

    Args:
        page: 页码，从 1 开始。
        page_size: 每页条数，最大 100。
        keyword: 可选，按用户名模糊搜索。

    Returns:
        未登录返回 ``LOGIN_REQUIRED_MSG``；
        否则 JSON：``{"total": int, "items": [精简用户, ...]}``。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

    db = _require_db()
    page_size = _clamp_page_size(page_size)
    skip = (page - 1) * page_size
    total, items = crud.list_users(db, skip=skip, limit=page_size, keyword=keyword)
    return _json(
        {
            "total": total,
            "items": [_user_summary_dict(u) for u in items],
        }
    )


class GetUserArgs(BaseModel):
    """get_user 入参。"""

    user_id: int = Field(..., ge=1, description="用户 ID")


def _get_user(user_id: int) -> str:
    """按 ID 查询单个用户（不含密码）。

    Args:
        user_id: 用户主键。

    Returns:
        未登录 / 不存在时返回对应错误；成功返回用户公开字段 JSON。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

    db = _require_db()
    user = crud.get_user(db, user_id)
    if user is None:
        return _json({"error": "用户不存在"})
    return _json(_user_dict(user))


class CreateUserArgs(BaseModel):
    """create_user 入参。"""

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    email: str | None = Field(None, description="邮箱")


def _create_user(username: str, password: str, email: str | None = None) -> str:
    """创建新用户；用户名 / 邮箱不可与已有记录冲突。

    Args:
        username: 用户名，长度 3–50。
        password: 明文密码，长度 6–128（落库前会哈希）。
        email: 可选邮箱。

    Returns:
        未登录 / 冲突 / 参数无效时返回 ``{"error": "..."}``；
        成功返回 ``{"ok": True, "user": {...}}``，并标记 users 变更。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

    db = _require_db()
    if crud.get_user_by_username(db, username):
        return _json({"error": "用户名已存在"})
    if email and crud.get_user_by_email(db, email):
        return _json({"error": "邮箱已被使用"})

    try:
        payload = schemas.UserRegister(
            username=username, password=password, email=email
        )
    except Exception as exc:
        return _json({"error": f"参数无效：{exc}"})

    user = crud.create_user(db, payload, security.hash_password(password))
    _mark_mutation("users")
    return _json({"ok": True, "user": _user_dict(user)})


class UpdateUserArgs(BaseModel):
    """update_user 入参；仅传需要修改的字段。"""

    user_id: int = Field(..., ge=1, description="用户 ID")
    username: str | None = Field(
        None, min_length=3, max_length=50, description="新用户名"
    )
    email: str | None = Field(None, description="新邮箱")
    password: str | None = Field(
        None, min_length=6, max_length=128, description="新密码"
    )


def _update_user(
    user_id: int,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> str:
    """按 ID 更新用户资料；用户名 / 邮箱冲突时拒绝。

    Args:
        user_id: 用户主键。
        username: 新用户名；None 表示不改。
        email: 新邮箱；None 表示不改。
        password: 新明文密码；None 表示不改，有值时会重新哈希。

    Returns:
        未登录 / 不存在 / 冲突时返回对应 error；
        成功返回 ``{"ok": True, "user": {...}}``，并标记 users 变更。
    """
    login_error = _login_error()
    if login_error is not None:
        return login_error

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
    """delete_user 入参。"""

    user_id: int = Field(..., ge=1, description="用户 ID")


def _delete_user(user_id: int) -> str:
    """按 ID 删除用户；禁止删除当前登录用户自己。

    Args:
        user_id: 要删除的用户主键。

    Returns:
        未登录 / 删自己 / 不存在时返回对应错误；
        成功返回 ``{"ok": True, "deleted_id": id}``，并标记 users 变更。
    """
    current = _current_user()
    if current is None:
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


# ===========================================================================
# 工具注册表
# ===========================================================================


def build_tools() -> list[BaseTool]:
    """构造本应用全部助手工具，供 ChatOllama.bind_tools 使用。

    Returns:
        StructuredTool 列表，顺序：商品 CRUD → 用户 CRUD。
    """
    return [
        _make_tool(
            func=_list_products,
            name="list_products",
            description="分页查询商品列表，可按名称关键字搜索。",
            args_schema=ListProductsArgs,
        ),
        _make_tool(
            func=_get_product,
            name="get_product",
            description="按 ID 查询单个商品详情。",
            args_schema=GetProductArgs,
        ),
        _make_tool(
            func=_create_product,
            name="create_product",
            description=(
                "创建新商品。名称必填；描述、价格、库存可选，缺省时可传合理示例值。"
                "商品名称不可与已有商品重复。"
            ),
            args_schema=CreateProductArgs,
        ),
        _make_tool(
            func=_update_product,
            name="update_product",
            description=(
                "按 ID 更新单个商品字段（仅传需要修改的字段，不要传 null）。"
                "一次要改多个商品时，请在同一轮并行多次调用本工具。"
            ),
            args_schema=UpdateProductArgs,
        ),
        _make_tool(
            func=_delete_product,
            name="delete_product",
            description="按 ID 删除商品。",
            args_schema=DeleteProductArgs,
        ),
        _make_tool(
            func=_list_users,
            name="list_users",
            description="分页查询用户列表，可按用户名关键字搜索。",
            args_schema=ListUsersArgs,
        ),
        _make_tool(
            func=_get_user,
            name="get_user",
            description="按 ID 查询单个用户（不含密码）。",
            args_schema=GetUserArgs,
        ),
        _make_tool(
            func=_create_user,
            name="create_user",
            description="创建新用户（用户名、密码、可选邮箱）。",
            args_schema=CreateUserArgs,
        ),
        _make_tool(
            func=_update_user,
            name="update_user",
            description="按 ID 更新用户（用户名、邮箱、密码均可选）。",
            args_schema=UpdateUserArgs,
        ),
        _make_tool(
            func=_delete_user,
            name="delete_user",
            description="按 ID 删除用户（不能删除当前登录用户自己）。",
            args_schema=DeleteUserArgs,
        ),
    ]
