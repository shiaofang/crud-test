from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="商品名称")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="描述")
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, comment="价格")
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="库存")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
