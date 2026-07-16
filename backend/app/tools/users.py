"""用户 CRUD 工具。"""

from __future__ import annotations

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .. import crud, schemas, security
from ._make import _DEFAULT_PAGE_SIZE, _PaginationArgs, _clamp_page_size
from .context import _require_db, with_tool_session
from .serialize import _json, _user_dict, _user_summary_dict


class ListUsersArgs(_PaginationArgs):
    keyword: str | None = Field(None, description="按用户名模糊搜索")


class GetUserArgs(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")


class CreateUserArgs(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    email: str | None = Field(None, description="邮箱")


class UpdateUserArgs(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    username: str | None = Field(
        None, min_length=3, max_length=50, description="新用户名"
    )
    email: str | None = Field(None, description="新邮箱")
    password: str | None = Field(
        None, min_length=6, max_length=128, description="新密码"
    )


class DeleteUserArgs(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")


@tool("list_users", args_schema=ListUsersArgs)
@with_tool_session
def list_users(
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    keyword: str | None = None,
) -> str:
    """分页查询用户列表，可按用户名关键字搜索。"""
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


@tool("get_user", args_schema=GetUserArgs)
@with_tool_session
def get_user(user_id: int) -> str:
    """按 ID 查询单个用户（不含密码）。"""
    db = _require_db()
    user = crud.get_user(db, user_id)
    if user is None:
        return _json({"error": "用户不存在"})
    return _json(_user_dict(user))


@tool("create_user", args_schema=CreateUserArgs)
@with_tool_session
def create_user(username: str, password: str, email: str | None = None) -> str:
    """创建新用户（用户名、密码、可选邮箱）。"""
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
    return _json({"ok": True, "user": _user_dict(user)})


@tool("update_user", args_schema=UpdateUserArgs)
@with_tool_session
def update_user(
    user_id: int,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> str:
    """按 ID 更新用户（用户名、邮箱、密码均可选）。"""
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
    return _json({"ok": True, "user": _user_dict(updated)})


@tool("delete_user", args_schema=DeleteUserArgs)
@with_tool_session
def delete_user(user_id: int) -> str:
    """按 ID 删除用户。"""
    db = _require_db()
    user = crud.get_user(db, user_id)
    if user is None:
        return _json({"error": "用户不存在"})

    crud.delete_user(db, user)
    return _json({"ok": True, "deleted_id": user_id})


USER_TOOLS: list[BaseTool] = [
    list_users,
    get_user,
    create_user,
    update_user,
    delete_user,
]
