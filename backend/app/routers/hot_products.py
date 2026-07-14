"""热门商品：从商品表按点击量取 Top 3，公开可读。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/hot-products", tags=["hot-products"])


@router.get("", response_model=schemas.ProductList)
def list_hot_products(
    keyword: str | None = Query(None, description="按商品名称模糊搜索"),
    db: Session = Depends(get_db),
) -> schemas.ProductList:
    """返回点击量 Top 3 的商品（无需登录）。"""
    items = crud.get_hot_products(db, limit=3, keyword=keyword)
    return schemas.ProductList(total=len(items), items=items)
