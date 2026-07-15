"""认证工具：密码哈希与 JWT 令牌。"""

from datetime import datetime, timedelta, timezone

from bcrypt import checkpw, gensalt, hashpw
from jose import JWTError, jwt

from .config import settings


def hash_password(password: str) -> str:
    """把明文密码哈希后返回字符串，存入数据库。

    Args:
        password: 用户输入的明文密码。

    Returns:
        bcrypt 哈希字符串（可安全入库）。
    """
    password_bytes = password.encode()
    hashed_bytes = hashpw(password_bytes, gensalt())
    return hashed_bytes.decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码是否与库中哈希匹配。

    Args:
        plain_password: 登录时用户输入的明文密码。
        hashed_password: 数据库里保存的哈希。

    Returns:
        匹配返回 True，否则 False。
    """
    plain_bytes = plain_password.encode()
    hashed_bytes = hashed_password.encode()
    return checkpw(plain_bytes, hashed_bytes)


def create_access_token(subject: str) -> str:
    """为指定主体（通常是用户名）签发 JWT access token。

    Args:
        subject: 写入 JWT ``sub`` 字段的标识，本项目用用户名。

    Returns:
        编码后的 JWT 字符串。
    """
    expire_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    payload = {
        "sub": subject,
        "exp": expire_at,
    }
    token = jwt.encode(
        claims=payload,
        key=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token


def decode_access_token(token: str) -> str | None:
    """解析 JWT，成功则返回 ``sub``（用户名），失败返回 None。

    Args:
        token: 前端传来的 Bearer Token 字符串。

    Returns:
        用户名字符串；令牌无效、过期或格式错误时返回 None。
    """
    try:
        payload = jwt.decode(
            token=token,
            key=settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        if isinstance(subject, str):
            return subject
        return None
    except JWTError:
        return None
