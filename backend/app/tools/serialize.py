"""工具返回给模型的 JSON / 字典形状。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .. import models


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _product_dict(product: models.Product) -> dict[str, Any]:
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
    return {
        "id": product.id,
        "name": product.name,
        "price": float(product.price),
        "stock": product.stock,
    }


def _user_dict(user: models.User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at,
    }


def _user_summary_dict(user: models.User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
    }
