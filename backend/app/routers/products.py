"""商品资源的 CRUD 路由。

路由只负责参数解析、调用 crud 层并组织响应；
「查不到即 404」的逻辑统一交给 get_product_or_404 依赖处理。
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..dependencies import get_current_user, get_product_or_404

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=schemas.ProductList)
def list_products(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: str | None = Query(None, description="按商品名称模糊搜索"),
    db: Session = Depends(get_db),
) -> schemas.ProductList:
    """分页查询商品列表，支持按名称关键字模糊搜索。"""
    skip = (page - 1) * page_size
    total, items = crud.get_products(db, skip=skip, limit=page_size, keyword=keyword)
    return schemas.ProductList(total=total, items=items)


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(product: models.Product = Depends(get_product_or_404)) -> models.Product:
    """获取单个商品详情。"""
    return product


@router.post("", response_model=schemas.ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> models.Product:
    """创建商品。"""
    return crud.create_product(db, payload)


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    payload: schemas.ProductUpdate,
    product: models.Product = Depends(get_product_or_404),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> models.Product:
    """更新商品，仅覆盖请求中显式传入的字段。"""
    return crud.update_product(db, product, payload)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product: models.Product = Depends(get_product_or_404),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> None:
    """删除商品。"""
    crud.delete_product(db, product)
