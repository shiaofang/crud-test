"""应用配置：从环境变量 / .env 读取，集中管理数据库与 CORS 等设置。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用运行所需的全部配置项。"""

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "crud_demo"
    cors_origins: str = "http://localhost:5173"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

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
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
