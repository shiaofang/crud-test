"""应用入口：负责创建 FastAPI 实例、挂载中间件并注册路由。

具体业务逻辑分布在各分层模块中：
- config    应用配置
- database  数据库连接与会话
- models    ORM 数据模型
- schemas   请求/响应数据模型
- crud      数据访问逻辑
- routers   HTTP 路由
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, SessionLocal, engine
from .routers import auth, health, hot_products, products
from .seed import seed_hot_products

API_PREFIX = "/api"

Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    seed_hot_products(db)

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
