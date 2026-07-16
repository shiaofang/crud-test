"""请求级工具上下文：用 ContextVar 注入 db。

不把 Session 做成工具参数；每请求在 chat_stream 里 set，结束时 reset。
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from functools import wraps
from typing import Any

from sqlalchemy.orm import Session

from ..database import SessionLocal

_db_var: ContextVar[Session | None] = ContextVar("tool_db", default=None)


def set_tool_context(db: Session) -> Token:
    """绑定本轮请求的 Session；返回值须交给 reset_tool_context。"""
    return _db_var.set(db)


def reset_tool_context(db_token: Token) -> None:
    """还原 set_tool_context 写入的 ContextVar。"""
    _db_var.reset(db_token)


def run_with_tool_session(fn: Callable[[], str]) -> str:
    """在短生命周期 Session 中执行工具。"""
    db = SessionLocal()
    db_token = _db_var.set(db)
    try:
        return fn()
    finally:
        try:
            db.close()
        except Exception:
            pass
        _db_var.reset(db_token)


def with_tool_session(func: Callable[..., str]) -> Callable[..., str]:
    """装饰器：工具执行前自动开 Session。配合 @tool 使用，写在 @tool 下面。"""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        return run_with_tool_session(lambda: func(*args, **kwargs))

    return wrapper


def _require_db() -> Session:
    db = _db_var.get()
    if db is None:
        raise RuntimeError("工具上下文未初始化")
    return db
