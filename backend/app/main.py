"""应用入口：负责创建 FastAPI 实例、挂载中间件并注册路由。

`app` 为 Python 包（含 `__init__.py`），通过 `uvicorn app.main:app` 启动。
具体业务逻辑分布在各分层模块中：
- config    应用配置
- database  数据库连接与会话
- models    ORM 数据模型
- schemas   请求/响应数据模型
- crud      数据访问逻辑
- routers   HTTP 路由子包
- llm       智能助手（大模型 + 工具调用）
- tools     智能助手可调用的数据库工具
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import auth, chat, health, products

API_PREFIX = "/api"

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(title="智能商城管理系统 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(products.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
