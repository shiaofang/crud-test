"""应用配置：从环境变量 / .env 读取，集中管理数据库与 CORS 等设置。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用运行所需的全部配置项（可从环境变量 / .env 覆盖）。"""

    # MySQL
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "crud_demo"

    # 前端地址，多个用英文逗号分隔
    cors_origins: str = "http://localhost:5173"

    # JWT 登录令牌
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    # Ollama Cloud（https://ollama.com）
    ollama_api_key: str = ""
    ollama_base_url: str = "https://ollama.com"
    ollama_model: str = "gpt-oss:120b"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        """拼装 SQLAlchemy 使用的 MySQL 连接串。"""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        """将逗号分隔的 CORS 白名单解析为列表。"""
        origins: list[str] = []
        for origin in self.cors_origins.split(","):
            cleaned = origin.strip()
            if cleaned:
                origins.append(cleaned)
        return origins


# 进程内单例：其它模块通过 from app.config import settings 使用
settings = Settings()
