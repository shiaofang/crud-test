"""智能助手数据库工具（商品 + 用户）。

对外 API：set_tool_context / reset_tool_context / build_tools。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from .context import reset_tool_context, set_tool_context
from .products import PRODUCT_TOOLS
from .users import USER_TOOLS

__all__ = [
    "build_tools",
    "reset_tool_context",
    "set_tool_context",
]


def build_tools() -> list[BaseTool]:
    """全部助手工具：商品 CRUD → 用户 CRUD。"""
    return [*PRODUCT_TOOLS, *USER_TOOLS]
