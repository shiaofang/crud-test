"""分页入参基类。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100


def _clamp_page_size(
    value: Any,
    *,
    default: int = _DEFAULT_PAGE_SIZE,
    maximum: int = _MAX_PAGE_SIZE,
) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, maximum))


class _PaginationArgs(BaseModel):
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
