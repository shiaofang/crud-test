# 全栈 CRUD 示例（商品管理）

一个用于练手的最小全栈项目，实现「商品」表的增删改查。

- **前端**：Vue 3 + TypeScript + Vite + Element Plus
- **后端**：Python + FastAPI + SQLAlchemy
- **数据库**：MySQL

```
test/
├── backend/            # FastAPI 后端
│   ├── app/
│   │   ├── main.py     # 路由入口
│   │   ├── config.py   # 读取 .env 配置
│   │   ├── database.py # 数据库连接
│   │   ├── models.py   # ORM 模型
│   │   ├── schemas.py  # Pydantic 校验模型
│   │   └── crud.py     # 增删改查逻辑
│   ├── requirements.txt
│   └── .env.example
├── frontend/           # Vue3 前端
│   └── src/
│       ├── App.vue     # 主界面（表格 + 弹窗表单）
│       ├── api.ts      # axios 封装
│       └── types.ts
└── DEPLOY.md           # Ubuntu 22.04 部署指南
```

## 本地开发

### 1. 后端

先确保本地有一个 MySQL，并创建数据库：

```sql
CREATE DATABASE crud_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

然后：

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt

# 复制配置并填入你的数据库账号密码
copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux

uvicorn app.main:app --reload --port 8000
```

启动后访问 http://127.0.0.1:8000/docs 可以看到自动生成的接口文档。
表 `products` 会在首次启动时自动创建。

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 即可。开发服务器已配置代理，会把 `/api` 转发到 `http://127.0.0.1:8000`，所以不用担心跨域。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/products?page=1&page_size=10&keyword=` | 分页查询 |
| GET | `/api/products/{id}` | 查询单个 |
| POST | `/api/products` | 新增 |
| PUT | `/api/products/{id}` | 更新 |
| DELETE | `/api/products/{id}` | 删除 |

## 部署

见 [DEPLOY.md](./DEPLOY.md)。
