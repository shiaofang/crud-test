"""认证工具：密码哈希与 JWT 令牌。"""

from datetime import datetime, timedelta, timezone

from bcrypt import checkpw, gensalt, hashpw
from jose import JWTError, jwt

from .config import settings


def hash_password(password: str) -> str:
    return hashpw(password.encode(), gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return checkpw(plain.encode(), hashed.encode())


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": subject, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        sub = payload.get("sub")
        return sub if isinstance(sub, str) else None
    except JWTError:
        return None
