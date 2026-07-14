"""数据访问层：封装对 Product 表的增删改查，路由层只与本模块交互。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas


def get_product(db: Session, product_id: int) -> models.Product | None:
    """按主键查询单个商品，不存在时返回 None。"""
    return db.get(models.Product, product_id)


def get_product_by_name(
    db: Session, name: str, *, exclude_id: int | None = None
) -> models.Product | None:
    """按名称精确查询商品；exclude_id 用于更新时排除自身。"""
    name = name.strip()
    if not name:
        return None
    stmt = select(models.Product).where(models.Product.name == name)
    if exclude_id is not None:
        stmt = stmt.where(models.Product.id != exclude_id)
    return db.execute(stmt).scalar_one_or_none()


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


def get_hot_products(
    db: Session, limit: int = 3, keyword: str | None = None
) -> list[models.Product]:
    """按点击量取热门商品（默认 Top 3）。"""
    stmt = select(models.Product)
    if keyword:
        stmt = stmt.where(models.Product.name.like(f"%{keyword}%"))
    items = (
        db.execute(
            stmt.order_by(models.Product.clickCount.desc(), models.Product.id.desc()).limit(
                limit
            )
        )
        .scalars()
        .all()
    )
    return list(items)


def create_product(db: Session, product: schemas.ProductCreate) -> models.Product:
    """创建并持久化商品，返回落库后的实例。名称不可与已有商品重复。"""
    if get_product_by_name(db, product.name):
        raise ValueError("商品名称已存在，不能重复添加")
    data = product.model_dump()
    data["name"] = data["name"].strip()
    db_product = models.Product(**data)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def update_product(
    db: Session, db_product: models.Product, product: schemas.ProductUpdate
) -> models.Product:
    """按传入字段增量更新商品（未显式传入或为 None 的字段保持不变）。"""
    data = product.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in data:
        data["name"] = data["name"].strip()
        if not data["name"]:
            raise ValueError("商品名称不能为空")
        if get_product_by_name(db, data["name"], exclude_id=db_product.id):
            raise ValueError("商品名称已存在，不能与其他商品重名")
    for field, value in data.items():
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
    """创建并持久化用户，返回落库后的实例。"""
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def list_users(
    db: Session, skip: int = 0, limit: int = 20, keyword: str | None = None
) -> tuple[int, list[models.User]]:
    """分页查询用户，返回 (总数, 当前页列表)；keyword 存在时按用户名模糊匹配。"""
    stmt = select(models.User)
    count_stmt = select(func.count()).select_from(models.User)

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(models.User.username.like(pattern))
        count_stmt = count_stmt.where(models.User.username.like(pattern))

    total = db.execute(count_stmt).scalar_one()
    items = (
        db.execute(
            stmt.order_by(models.User.id.desc()).offset(skip).limit(limit)
        )
        .scalars()
        .all()
    )
    return total, list(items)


def update_user(
    db: Session,
    db_user: models.User,
    *,
    username: str | None = None,
    email: str | None = None,
    hashed_password: str | None = None,
) -> models.User:
    """按传入字段增量更新用户（未显式传入的字段保持不变）。"""
    if username is not None:
        db_user.username = username
    if email is not None:
        db_user.email = email
    if hashed_password is not None:
        db_user.hashed_password = hashed_password
    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, db_user: models.User) -> None:
    """删除指定用户。"""
    db.delete(db_user)
    db.commit()
