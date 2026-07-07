# 全栈 CRUD 示例（商品管理）

一个用于练手的最小全栈项目，实现「商品」表的增删改查。

- **前端**：Vue 3 + TypeScript + Vite + Element Plus
- **后端**：Python + FastAPI + SQLAlchemy
- **数据库**：MySQL

```
crud-app/
├── backend/                # FastAPI 后端
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/               # Vue3 前端
│   ├── Dockerfile          # 多阶段构建：npm build + nginx
│   └── src/
├── docker/
│   └── nginx.conf          # Nginx 反向代理配置
├── .github/workflows/
│   └── ci-cd.yml           # push main 自动构建 & 部署
├── docker-compose.yml      # 本地 Docker 开发
├── docker-compose.prod.yml # 生产环境（使用 GHCR 镜像）
└── DEPLOY.md               # Ubuntu 裸机部署指南
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

## Docker 本地运行

在项目根目录复制环境变量并启动全部服务（MySQL + 后端 + Nginx）：

```bash
cp .env.example .env
# 编辑 .env，至少修改 DB_PASSWORD

docker compose up -d --build
```

浏览器访问 http://localhost 。前端在镜像构建阶段完成打包，无需手动 `npm run build` 或 scp `dist/`。

## CI/CD 自动部署

push 到 `main` 分支时，GitHub Actions 会：

1. 构建并校验前端
2. 构建 backend / nginx 镜像并推送到 GHCR
3. SSH 到服务器执行 `docker compose pull && up -d`

### 服务器一次性准备

```bash
# 安装 Docker 与 Compose 插件
curl -fsSL https://get.docker.com | sh

mkdir -p /opt/crud-app
```

安全组放行 **80** 端口。

### GitHub Secrets 配置

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret | 说明 |
| --- | --- |
| `SERVER_HOST` | 服务器公网 IP |
| `SERVER_USER` | SSH 用户名，如 `root` |
| `SSH_PRIVATE_KEY` | SSH 私钥全文 |
| `DB_PASSWORD` | MySQL root 密码 |
| `CORS_ORIGINS` | 前端访问地址，如 `http://8.136.47.107` |
| `GHCR_PULL_TOKEN` | GitHub PAT，`read:packages` 权限，用于服务器拉私有镜像 |

首次 push 到 main 后，Actions 会自动完成构建与发布。

### 镜像命名

- `ghcr.io/<owner>/<repo>-backend:<sha>`
- `ghcr.io/<owner>/<repo>-nginx:<sha>`

## 裸机部署（传统方式）

见 [DEPLOY.md](./DEPLOY.md)。
