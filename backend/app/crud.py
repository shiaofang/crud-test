"""数据访问层：封装对 Product 表的增删改查，路由层只与本模块交互。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas


def get_product(db: Session, product_id: int) -> models.Product | None:
    """按主键查询单个商品，不存在时返回 None。"""
    return db.get(models.Product, product_id)


def get_products(
    db: Session, skip: int = 0, limit: int = 20, keyword: str | None = None
) -> tuple[int, list[models.Product]]:
    """分页查询商品，返回 (总数, 当前页列表)；keyword 存在时按名称模糊匹配。"""
    stmt = select(models.Product)
    count_stmt = select(func.count()).select_from(models.Product)

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(models.Product.name.like(pattern))
        count_stmt = count_stmt.where(models.Product.name.like(pattern))

    total = db.execute(count_stmt).scalar_one()
    items = (
        db.execute(
            stmt.order_by(models.Product.id.desc()).offset(skip).limit(limit)
        )
        .scalars()
        .all()
    )
    return total, list(items)


def create_product(db: Session, product: schemas.ProductCreate) -> models.Product:
    """创建并持久化商品，返回落库后的实例。"""
    db_product = models.Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def update_product(
    db: Session, db_product: models.Product, product: schemas.ProductUpdate
) -> models.Product:
    """按传入字段增量更新商品（未显式传入的字段保持不变）。"""
    for field, value in product.model_dump(exclude_unset=True).items():
        setattr(db_product, field, value)
    db.commit()
    db.refresh(db_product)
    return db_product


def delete_product(db: Session, db_product: models.Product) -> None:
    """删除指定商品。"""
    db.delete(db_product)
    db.commit()


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.execute(
        select(models.User).where(models.User.username == username)
    ).scalar_one_or_none()


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.execute(
        select(models.User).where(models.User.email == email)
    ).scalar_one_or_none()


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def create_user(db: Session, user: schemas.UserRegister, hashed_password: str) -> models.User:
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_hot_product(db: Session, hot_product_id: int) -> models.HotProduct | None:
    return db.get(models.HotProduct, hot_product_id)


def get_hot_products(
    db: Session, skip: int = 0, limit: int = 20, keyword: str | None = None
) -> tuple[int, list[models.HotProduct]]:
    stmt = select(models.HotProduct)
    count_stmt = select(func.count()).select_from(models.HotProduct)

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(models.HotProduct.name.like(pattern))
        count_stmt = count_stmt.where(models.HotProduct.name.like(pattern))

    total = db.execute(count_stmt).scalar_one()
    items = (
        db.execute(
            stmt.order_by(models.HotProduct.sort_order.asc(), models.HotProduct.id.desc())
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return total, list(items)


def create_hot_product(db: Session, product: schemas.HotProductCreate) -> models.HotProduct:
    db_product = models.HotProduct(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def update_hot_product(
    db: Session, db_product: models.HotProduct, product: schemas.HotProductUpdate
) -> models.HotProduct:
    for field, value in product.model_dump(exclude_unset=True).items():
        setattr(db_product, field, value)
    db.commit()
    db.refresh(db_product)
    return db_product


def delete_hot_product(db: Session, db_product: models.HotProduct) -> None:
    db.delete(db_product)
    db.commit()


def count_hot_products(db: Session) -> int:
    return db.execute(select(func.count()).select_from(models.HotProduct)).scalar_one()
