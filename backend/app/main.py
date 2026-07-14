"""应用入口：负责创建 FastAPI 实例、挂载中间件并注册路由。

`app` 为 Python 包（含 `__init__.py`），通过 `uvicorn app.main:app` 启动。
具体业务逻辑分布在各分层模块中：
- config    应用配置
- database  数据库连接与会话
- models    ORM 数据模型
- schemas   请求/响应数据模型
- crud      数据访问逻辑
- routers   HTTP 路由子包
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import settings
from .database import Base, engine
from .routers import auth, health, hot_products, products

API_PREFIX = "/api"

Base.metadata.create_all(bind=engine)

with engine.begin() as conn:
    # 热门商品已改为按商品表点击量统计，删除旧表（若存在）
    conn.execute(text("DROP TABLE IF EXISTS hot_products"))
    # 已有库补齐点击量字段
    columns = {col["name"] for col in inspect(engine).get_columns("products")}
    if "clickCount" not in columns:
        conn.execute(
            text(
                "ALTER TABLE products ADD COLUMN clickCount INT NOT NULL DEFAULT 0 "
                "COMMENT '点击量'"
            )
        )

app = FastAPI(title="商品管理 CRUD API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(hot_products.router, prefix=API_PREFIX)
app.include_router(products.router, prefix=API_PREFIX)
