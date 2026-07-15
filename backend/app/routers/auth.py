"""用户认证路由：注册、登录、获取当前用户信息。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas, security
from ..database import get_db
from ..dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: schemas.UserRegister,
    db: Session = Depends(get_db),
) -> models.User:
    """注册新用户。"""
    existing_by_username = crud.get_user_by_username(db, payload.username)
    if existing_by_username is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    if payload.email:
        existing_by_email = crud.get_user_by_email(db, payload.email)
        if existing_by_email is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被注册",
            )

    hashed_password = security.hash_password(payload.password)
    user = crud.create_user(db, payload, hashed_password)
    return user


@router.post("/login", response_model=schemas.Token)
def login(
    payload: schemas.UserLogin,
    db: Session = Depends(get_db),
) -> schemas.Token:
    """用户名密码登录，返回 JWT。"""
    user = crud.get_user_by_username(db, payload.username)
    password_ok = (
        user is not None
        and security.verify_password(payload.password, user.hashed_password)
    )
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    access_token = security.create_access_token(subject=user.username)
    return schemas.Token(access_token=access_token)


@router.get("/me", response_model=schemas.UserOut)
def me(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """获取当前登录用户信息。"""
    return current_user
