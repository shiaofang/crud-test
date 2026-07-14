"""ORM 数据模型：与数据库表结构一一对应。"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    """用户表。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="用户名")
    email: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, comment="邮箱")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Product(Base):
    """商品表。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="商品名称"
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="描述")
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, comment="价格")
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="库存")
    clickCount: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="点击量")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
