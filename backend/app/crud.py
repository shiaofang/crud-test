from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas


def get_product(db: Session, product_id: int) -> models.Product | None:
    return db.get(models.Product, product_id)


def get_products(
    db: Session, skip: int = 0, limit: int = 20, keyword: str | None = None
) -> tuple[int, list[models.Product]]:
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
    db_product = models.Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def update_product(
    db: Session, db_product: models.Product, product: schemas.ProductUpdate
) -> models.Product:
    for field, value in product.model_dump(exclude_unset=True).items():
        setattr(db_product, field, value)
    db.commit()
    db.refresh(db_product)
    return db_product


def delete_product(db: Session, db_product: models.Product) -> None:
    db.delete(db_product)
    db.commit()
