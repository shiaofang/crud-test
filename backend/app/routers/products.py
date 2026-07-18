"""商品资源的 CRUD 路由。

路由只负责参数解析、调用 crud 层并组织响应；
「查不到即 404」的逻辑统一交给 get_product_or_404 依赖处理。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..dependencies import get_current_user, get_product_or_404
from ..kafka_bus import emit_product_activity

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
    total, items = crud.get_products(
        db,
        skip=skip,
        limit=page_size,
        keyword=keyword,
    )
    return schemas.ProductList(
        total=total,
        items=[schemas.ProductOut.model_validate(item) for item in items],
    )


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(
    product: models.Product = Depends(get_product_or_404),
) -> models.Product:
    """获取单个商品详情。"""
    return product


@router.post(
    "",
    response_model=schemas.ProductOut,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.Product:
    """创建商品（名称不可重复）。需要登录。"""
    try:
        product = crud.create_product(db, payload)
        emit_product_activity(
            action="created",
            product_id=product.id,
            product_name=product.name,
            source="admin",
            actor=current_user.username,
        )
        return product
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    payload: schemas.ProductUpdate,
    product: models.Product = Depends(get_product_or_404),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.Product:
    """更新商品，仅覆盖请求中显式传入的字段。需要登录。"""
    changes: dict = {}
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != product.name:
        changes["name"] = (product.name, data["name"])
    if "price" in data and float(data["price"]) != float(product.price):
        changes["price"] = (float(product.price), float(data["price"]))
    if "stock" in data and data["stock"] != product.stock:
        changes["stock"] = (product.stock, data["stock"])
    if "description" in data and data["description"] != product.description:
        changes["description"] = True

    try:
        updated = crud.update_product(db, product, payload)
        emit_product_activity(
            action="updated",
            product_id=updated.id,
            product_name=updated.name,
            source="admin",
            actor=current_user.username,
            changes=changes or None,
        )
        return updated
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product: models.Product = Depends(get_product_or_404),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> None:
    """删除商品。需要登录。"""
    product_id = product.id
    product_name = product.name
    crud.delete_product(db, product)
    emit_product_activity(
        action="deleted",
        product_id=product_id,
        product_name=product_name,
        source="admin",
        actor=current_user.username,
    )
