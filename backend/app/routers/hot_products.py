"""热门商品路由：首页公开展示，增删改需登录。"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..dependencies import get_current_user, get_hot_product_or_404

router = APIRouter(prefix="/hot-products", tags=["hot-products"])


@router.get("", response_model=schemas.HotProductList)
def list_hot_products(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(12, ge=1, le=100, description="每页数量"),
    keyword: str | None = Query(None, description="按商品名称模糊搜索"),
    db: Session = Depends(get_db),
) -> schemas.HotProductList:
    """分页查询热门商品（公开，无需登录）。"""
    skip = (page - 1) * page_size
    total, items = crud.get_hot_products(db, skip=skip, limit=page_size, keyword=keyword)
    return schemas.HotProductList(total=total, items=items)


@router.get("/{hot_product_id}", response_model=schemas.HotProductOut)
def get_hot_product(
    product: models.HotProduct = Depends(get_hot_product_or_404),
) -> models.HotProduct:
    """获取单个热门商品详情（公开，无需登录）。"""
    return product


@router.post("", response_model=schemas.HotProductOut, status_code=status.HTTP_201_CREATED)
def create_hot_product(
    payload: schemas.HotProductCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> models.HotProduct:
    """创建热门商品（需登录）。"""
    return crud.create_hot_product(db, payload)


@router.put("/{hot_product_id}", response_model=schemas.HotProductOut)
def update_hot_product(
    payload: schemas.HotProductUpdate,
    product: models.HotProduct = Depends(get_hot_product_or_404),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> models.HotProduct:
    """更新热门商品（需登录）。"""
    return crud.update_hot_product(db, product, payload)


@router.delete("/{hot_product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hot_product(
    product: models.HotProduct = Depends(get_hot_product_or_404),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> None:
    """删除热门商品（需登录）。"""
    crud.delete_hot_product(db, product)
