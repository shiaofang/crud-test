"""FastAPI 依赖项：数据库会话、资源获取等可复用的注入逻辑。"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import crud, models, security
from .database import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def get_product_or_404(
    product_id: int,
    db: Session = Depends(get_db),
) -> models.Product:
    """按 ID 获取商品，不存在时统一抛出 404，供各路由复用。"""
    product = crud.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商品不存在",
        )
    return product


def get_hot_product_or_404(
    hot_product_id: int,
    db: Session = Depends(get_db),
) -> models.HotProduct:
    """按 ID 获取热门商品，不存在时抛出 404。"""
    product = crud.get_hot_product(db, hot_product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="热门商品不存在",
        )
    return product


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    """从 Bearer Token 解析当前登录用户。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或令牌无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = security.decode_access_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或令牌无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = crud.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
