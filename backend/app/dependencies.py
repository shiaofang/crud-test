"""FastAPI 依赖项：数据库会话、资源获取等可复用的注入逻辑。"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from . import crud, models
from .database import get_db


def get_product_or_404(
    product_id: int,
    db: Session = Depends(get_db),
) -> models.Product:
    """按 ID 获取商品，不存在时统一抛出 404，供各路由复用。"""
    product = crud.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商品不存在",
        )
    return product
