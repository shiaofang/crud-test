"""数据库配置：创建引擎、会话工厂与声明基类，并提供请求级会话依赖。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# 全局引擎：整个进程共用一个连接池
engine = create_engine(
    url=settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

# 会话工厂：每次调用 SessionLocal() 得到一个新的 Session
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：为单个请求提供数据库会话，请求结束后自动关闭。

    用法::

        def some_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
