# Docker + CI/CD 自动部署学习手册

> 本文档记录第一次在 **阿里云 ECS** 上通过 **Docker** 部署项目，并配合 **GitHub Actions** 实现 **push 即发布** 的完整流程与原理说明。  
> 裸机手动部署（Python venv + systemd + Nginx）见 [HANDLE_DEPLOY.md](./HANDLE_DEPLOY.md)，有助于对比理解各组件职责。

---

## 目录

1. [整体架构](#1-整体架构)
2. [为什么用 Docker + CI/CD](#2-为什么用-docker--cicd)
3. [项目中的关键文件](#3-项目中的关键文件)
4. [Docker 核心概念速览](#4-docker-核心概念速览)
5. [阶段一：本地用 Docker 跑通](#5-阶段一本地用-docker-跑通)
6. [阶段二：ECS 服务器一次性准备](#6-阶段二ecs-服务器一次性准备)
7. [阶段三：配置 GitHub Secrets](#7-阶段三配置-github-secrets)
8. [阶段四：CI/CD 流水线详解](#8-阶段四cicd-流水线详解)
9. [阶段五：首次发布与验证](#9-阶段五首次发布与验证)
10. [日常开发与发布](#10-日常开发与发布)
11. [常见问题排查](#11-常见问题排查)
12. [服务器常用运维命令](#12-服务器常用运维命令)
13. [与裸机部署的对比](#13-与裸机部署的对比)

---

## 1. 整体架构

### 1.1 请求链路

```
浏览器
  │
  ▼  HTTP :80
┌─────────────────────────────────────────────────┐
│  ECS 服务器 (/opt/crud-app)                      │
│                                                  │
│  ┌──────────┐    /api/*     ┌──────────┐         │
│  │  nginx   │ ────────────► │ backend  │         │
│  │  容器    │               │ FastAPI  │         │
│  │  :80     │    静态文件    │  :8000   │         │
│  │          │ ◄──────────── │          │         │
│  └──────────┘   /dist       └────┬─────┘         │
│       ▲                           │              │
│       │                           ▼              │
│  用户访问页面                 ┌──────────┐         │
│                               │  mysql   │         │
│                               │  :3306   │         │
│                               └──────────┘         │
└─────────────────────────────────────────────────┘
```

- **nginx 容器**：对外暴露 80 端口，托管前端静态文件，并把 `/api/` 反向代理到 backend。
- **backend 容器**：运行 FastAPI，连接同网络内的 `mysql` 服务名。
- **mysql 容器**：持久化数据卷 `mysql_data`，重启不丢数据。

### 1.2 CI/CD 发布链路

```
开发者 push 到 main
        │
        ▼
┌───────────────────┐
│  GitHub Actions   │
│  Job 1: build     │
│  · 构建 backend 镜像 │
│  · 构建 nginx 镜像  │  （前端在 nginx 镜像内 npm build）
│  · 推送到 GHCR     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Job 2: deploy    │
│  · SSH 连 ECS      │
│  · scp compose 文件│
│  · docker login   │
│  · pull 新镜像     │
│  · compose up -d  │
└─────────┬─────────┘
          │
          ▼
   浏览器访问 http://公网IP 看到新版本
```

**关键点**：服务器上**不装** Node、Python、Nginx、MySQL 本体，只装 Docker；代码变更由 GitHub 构建成镜像，服务器只负责 `pull` + `up`。

---

## 2. 为什么用 Docker + CI/CD

| 对比项 | 裸机部署（HANDLE_DEPLOY） | Docker + CI/CD（本方案） |
| --- | --- | --- |
| 环境安装 | 需 apt 装 Python、Nginx、MySQL | 只需装 Docker |
| 代码更新 | 本地 build + scp 上传 | `git push`，自动完成 |
| 依赖一致性 | 本地与服务器可能不一致 | 镜像锁定环境，到处一样 |
| 回滚 | 手动覆盖旧文件 | 改镜像 tag 或 redeploy 旧 sha |
| 学习成本 | 低（传统运维） | 中（需理解镜像/Compose/Actions） |
| 适合场景 | 学习 Linux 运维 | 小项目自动化交付、简历项目展示 |

---

## 3. 项目中的关键文件

```
crud-app/
├── backend/
│   ├── Dockerfile              # 后端镜像：Python + uvicorn
│   └── app/                    # FastAPI 业务代码（Python 包，含 __init__.py）
├── frontend/
│   └── Dockerfile              # 前端镜像：多阶段 node build + nginx
├── docker/
│   └── nginx.conf              # 容器内 Nginx 反代配置
├── docker-compose.yml          # 本地开发：本地 build 镜像
├── docker-compose.prod.yml     # 生产环境：使用 GHCR 预构建镜像
├── .env.example                # 环境变量模板
├── .dockerignore               # 构建镜像时排除的文件
└── .github/workflows/ci-cd.yml # GitHub Actions 流水线
```

### 3.1 `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

| 行 | 说明 |
| --- | --- |
| `FROM python:3.11-slim` | 基于官方 Python 精简镜像 |
| `COPY requirements.txt` + `pip install` | 先装依赖，利用 Docker 层缓存加速重建 |
| `COPY app ./app` | 再拷贝业务代码 |
| `--host 0.0.0.0` | 监听容器内所有网卡，让同网络的 nginx 能访问 |
| `--workers 2` | 2 个 worker 进程，提高并发 |

### 3.2 `frontend/Dockerfile`（多阶段构建）

```dockerfile
# 阶段 1：用 Node 打包前端
FROM node:20-alpine AS builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# 阶段 2：只用 Nginx 托管 dist，最终镜像不含 Node
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

**多阶段构建的好处**：最终 nginx 镜像体积小，生产环境不需要 Node.js。

> 注意：`frontend/Dockerfile` 的构建上下文是**项目根目录**（`context: .`），所以 `COPY frontend/...` 路径从根目录写起。

### 3.3 `docker/nginx.conf`

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;

    location / {
        try_files $uri $uri/ /index.html;   # SPA 路由回退
    }

    location /api/ {
        set $backend_upstream backend;
        proxy_pass http://$backend_upstream:8000;
        # ... 传递 Host、真实 IP 等头
    }
}
```

| 配置 | 说明 |
| --- | --- |
| `try_files ... /index.html` | Vue Router history 模式刷新不 404 |
| `backend` | Docker Compose 服务名，容器间 DNS 解析 |
| `resolver 127.0.0.11` | Docker 内置 DNS；避免 nginx 启动时 backend 未就绪导致 upstream 地址被缓存 |

### 3.4 `docker-compose.yml` vs `docker-compose.prod.yml`

| | 本地 `docker-compose.yml` | 生产 `docker-compose.prod.yml` |
| --- | --- | --- |
| backend/nginx | `build:` 本地构建 | `image:` 使用 GHCR 镜像 |
| restart | `unless-stopped` | `always` |
| healthcheck | 仅 mysql | mysql + backend |
| nginx 依赖 | `depends_on: backend` | `depends_on: backend (healthy)` |

生产 compose 会等 backend 健康检查通过后再启动 nginx，减少「页面能开、接口 502」的窗口期。

### 3.5 `.dockerignore`

构建镜像时排除 `.git`、`node_modules`、`.env`、`*.md` 等，加快构建、避免把密钥打进镜像。

---

## 4. Docker 核心概念速览

| 概念 | 类比 | 在本项目中的体现 |
| --- | --- | --- |
| **镜像 Image** | 只读模板 / 安装包 | `ghcr.io/owner/repo-backend:abc123` |
| **容器 Container** | 镜像的运行实例 | `docker compose ps` 看到的 mysql/backend/nginx |
| **Compose** | 多容器编排脚本 | `docker-compose.prod.yml` 一次拉起三个服务 |
| **Volume** | 持久化磁盘 | `mysql_data` 存数据库文件，删容器不删数据 |
| **Network** | 容器虚拟局域网 | 服务名 `mysql`、`backend` 互相可解析 |
| **Registry** | 镜像仓库 | GHCR（GitHub Container Registry） |

常用命令：

```bash
docker compose ps              # 查看容器状态
docker compose logs -f backend # 跟踪后端日志
docker compose pull            # 拉取最新镜像
docker compose up -d           # 后台启动/更新
docker image prune -f          # 清理无用镜像，省磁盘
```

---

## 5. 阶段一：本地用 Docker 跑通

在推 ECS 之前，建议先在本地验证 Docker 方案能跑通。

### 5.1 准备环境变量

```bash
# 项目根目录
cp .env.example .env
# 编辑 .env，至少设置 DB_PASSWORD
```

`.env` 内容示例：

```env
DB_PASSWORD=你的强密码
CORS_ORIGINS=http://localhost
```

### 5.2 启动全部服务

```bash
docker compose up -d --build
```

| 参数 | 说明 |
| --- | --- |
| `up` | 创建并启动容器 |
| `-d` | 后台运行（detached） |
| `--build` | 启动前重新构建本地镜像 |

### 5.3 验证

```bash
# 查看三个容器是否都在运行
docker compose ps

# 测后端健康检查
curl http://localhost/api/health
# 期望：{"status":"ok"}

# 浏览器打开
# http://localhost
```

### 5.4 理解启动顺序

Compose 根据 `depends_on` + `healthcheck` 控制顺序：

1. **mysql** 先启动，healthcheck `mysqladmin ping` 通过后算 healthy
2. **backend** 等 mysql healthy 后启动，连接 `DB_HOST=mysql`
3. **nginx** 等 backend healthy 后启动（生产 compose）

表 `products` 由后端 `Base.metadata.create_all()` 在首次启动时自动创建，无需手动建表。

### 5.5 停止与清理

```bash
docker compose down          # 停止并删除容器（volume 保留）
docker compose down -v       # 连 mysql 数据卷一起删（慎用）
```

---

## 6. 阶段二：ECS 服务器一次性准备

以下操作只需做**一次**（换服务器时重做）。

### 6.1 购买与登录 ECS

1. 阿里云购买 ECS（建议 Ubuntu 22.04+，1 核 2G 起步练手够用）
2. 安全组 **入方向放行 80 端口**（HTTP）
3. SSH 登录：

```bash
ssh root@<你的公网IP>
```

### 6.2 安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
```

验证：

```bash
docker --version
docker compose version
```

### 6.3 创建部署目录

```bash
mkdir -p /opt/crud-app
```

生产环境所有 compose 相关文件放在 `/opt/crud-app/`（与裸机方案的 `/var/www/crud-app/` 不同）。

### 6.4 配置 SSH 密钥（供 GitHub Actions 登录）

**在本地电脑**生成专用于 CI 的密钥对（若已有可跳过）：

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/crud_deploy -N ""
```

**把公钥加到 ECS**：

```bash
# 查看公钥
cat ~/.ssh/crud_deploy.pub

# 在 ECS 上执行（把公钥内容粘贴进去）
mkdir -p ~/.ssh
echo "公钥整行内容" >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

**测试免密登录**：

```bash
ssh -i ~/.ssh/crud_deploy root@<你的公网IP>
```

私钥 `~/.ssh/crud_deploy`（无 `.pub` 后缀）全文将填入 GitHub Secret `SSH_PRIVATE_KEY`。

### 6.5 创建 GHCR 拉取 Token

服务器需要能从 GHCR 拉私有镜像（若仓库/包为 private）：

1. GitHub → **Settings → Developer settings → Personal access tokens**
2. 生成 Token，勾选 **`read:packages`**
3. 记下 Token，填入 Secret `GHCR_PULL_TOKEN`

---

## 7. 阶段三：配置 GitHub Secrets

路径：**仓库 Settings → Secrets and variables → Actions → New repository secret**

| Secret | 说明 | 示例 |
| --- | --- | --- |
| `SERVER_HOST` | ECS 公网 IP | `47.xxx.xxx.xxx` |
| `SERVER_USER` | SSH 用户名 | `root` |
| `SSH_PRIVATE_KEY` | 私钥全文（`BEGIN...END` 整段） | `~/.ssh/crud_deploy` 内容 |
| `DB_PASSWORD` | MySQL root 密码 | 强密码，与本地可不同 |
| `CORS_ORIGINS` | 允许跨域的前端地址 | `http://47.xxx.xxx.xxx` |
| `GHCR_PULL_TOKEN` | 拉镜像用 PAT | `ghp_xxxx`，权限 `read:packages` |

**注意**：

- `CORS_ORIGINS` 要写成用户浏览器实际访问的地址（带 `http://`，无端口号则默认 80）
- 若 Secret 值首尾有空格，workflow 里已对 `SERVER_HOST` / `SERVER_USER` 做了 `tr -d '[:space:]'` 处理
- `GITHUB_TOKEN` 由 Actions 自动提供，用于 push 镜像到 GHCR，**无需手动配置**

---

## 8. 阶段四：CI/CD 流水线详解

配置文件：`.github/workflows/ci-cd.yml`

### 8.1 触发条件

```yaml
on:
  push:
    branches: [main]       # push main → 构建 + 推送镜像 + 部署
  pull_request:
    branches: [main]       # PR → 仅构建校验，不推送、不部署
```

| 事件 | build 镜像 | push GHCR | deploy ECS |
| --- | --- | --- | --- |
| PR 到 main | ✅ | ❌ | ❌ |
| push 到 main | ✅ | ✅ | ✅ |

PR 只构建不部署，避免未合并代码上线。

### 8.2 Job 1：`build`（构建并推送镜像）

**步骤概览**：

```
checkout 代码
  → 安装 Docker Buildx（支持缓存）
  → 登录 GHCR（仅 main push）
  → 计算镜像名
  → 构建 backend 镜像并 push
  → 构建 nginx 镜像并 push
```

**镜像命名规则**：

```
ghcr.io/<owner>/<repo>-backend:<git-sha>
ghcr.io/<owner>/<repo>-backend:latest
ghcr.io/<owner>/<repo>-nginx:<git-sha>
ghcr.io/<owner>/<repo>-nginx:latest
```

- `<git-sha>`：本次 commit 的完整 hash，用于精确回滚
- `latest`：始终指向 main 最新构建

**构建缓存**：`cache-from/to: type=gha` 使用 GitHub Actions 缓存，加速后续构建。

### 8.3 Job 2：`deploy`（SSH 到 ECS 更新）

仅在 `push main` 时运行，且依赖 `build` 成功。

**步骤 1：准备 SSH**

```bash
# 把 Secret 里的私钥写到 ~/.ssh/deploy_key
# ssh-keyscan 把服务器 host key 加入 known_hosts（防 MITM 提示）
```

**步骤 2：拷贝 compose 文件**

```bash
ssh ... "mkdir -p /opt/crud-app"
scp docker-compose.prod.yml user@host:/opt/crud-app/
```

每次部署都会同步最新的 `docker-compose.prod.yml`（若你改了编排，无需手动上服务器改）。

**步骤 3：在服务器执行部署脚本**

等价于在 ECS 上手动执行：

```bash
cd /opt/crud-app

# 登录 GHCR 拉私有镜像
echo "<GHCR_PULL_TOKEN>" | docker login ghcr.io -u <github-actor> --password-stdin

# CI 动态生成本次部署用的环境文件
cat > .env.deploy << EOF
DB_PASSWORD=...
CORS_ORIGINS=...
BACKEND_IMAGE=ghcr.io/owner/repo-backend:<本次commit-sha>
NGINX_IMAGE=ghcr.io/owner/repo-nginx:<本次commit-sha>
EOF

# 拉取新镜像并滚动更新
docker compose --env-file .env.deploy -f docker-compose.prod.yml pull
docker compose --env-file .env.deploy -f docker-compose.prod.yml up -d

# 清理悬空镜像，释放磁盘
docker image prune -f
```

**`docker compose pull` + `up -d` 做了什么**：

1. `pull`：拉取 `.env.deploy` 里指定 sha 的新镜像
2. `up -d`：对比当前运行容器，有变更则**重建**对应容器，未变的保持运行
3. `mysql` 若配置未变且 volume 在，**数据不会丢**

---

## 9. 阶段五：首次发布与验证

### 9.1 触发首次部署

```bash
git add .
git commit -m "feat: enable docker ci/cd deploy"
git push origin main
```

打开 GitHub 仓库 **Actions** 页，查看 `CI/CD` workflow：

1. `build` job 绿灯 → 镜像已推到 GHCR（Packages 页可见）
2. `deploy` job 绿灯 → ECS 已更新

### 9.2 在 ECS 上验证

```bash
ssh root@<公网IP>
cd /opt/crud-app

# 容器状态
docker compose --env-file .env.deploy -f docker-compose.prod.yml ps

# 健康检查
curl -s http://127.0.0.1/api/health

# 查看后端日志
docker compose --env-file .env.deploy -f docker-compose.prod.yml logs -f backend
```

### 9.3 浏览器验证

访问 `http://<公网IP>`，测试商品的增删改查。

### 9.4 期望结果 checklist

| 检查项 | 期望 |
| --- | --- |
| Actions `build` | 成功，Packages 有两个镜像 |
| Actions `deploy` | 成功 |
| `docker compose ps` | mysql / backend / nginx 均为 Up (healthy) |
| `curl .../api/health` | `{"status":"ok"}` |
| 浏览器 | 页面正常，CRUD 可用 |

---

## 10. 日常开发与发布

### 10.1 推荐工作流

```
本地改代码
  → 本地 docker compose 或 npm/python 开发验证
  → 提 PR 到 main（Actions 自动 build 校验）
  → 合并 PR / 直接 push main
  → Actions 自动 build + deploy
  → 浏览器验证线上
```

### 10.2 你不需要再做的事

- ❌ 本地 `npm run build` 再 scp `dist/`
- ❌ 服务器上 `pip install`、配 venv
- ❌ 手动 `systemctl restart`
- ❌ 在服务器上装 Nginx / MySQL

### 10.3 你仍可能需要做的事

| 场景 | 操作 |
| --- | --- |
| 改了 `docker-compose.prod.yml` | push main，CI 会自动 scp 新文件并 `up -d` |
| 改了 Secrets（如换数据库密码） | 更新 GitHub Secret 后重新 push 或手动在服务器改 `.env.deploy` 再 `up -d` |
| 仅想重启服务 | SSH 后 `docker compose ... restart backend` |
| 回滚到上一版本 | 把 `.env.deploy` 里镜像 tag 改回旧 sha，再 `pull` + `up -d` |

### 10.4 回滚示例

```bash
cd /opt/crud-app
# 编辑 .env.deploy，把 BACKEND_IMAGE / NGINX_IMAGE 的 tag 改成旧 commit sha
nano .env.deploy
docker compose --env-file .env.deploy -f docker-compose.prod.yml pull
docker compose --env-file .env.deploy -f docker-compose.prod.yml up -d
```

旧 sha 可在 GitHub Actions 该次成功运行的 commit 或 Packages 镜像标签里找到。

---

## 11. 常见问题排查

| 现象 | 可能原因 | 排查 |
| --- | --- | --- |
| Actions `deploy` SSH 失败 | 私钥与服务器公钥不匹配 | 本地 `ssh -i 私钥 user@host` 测试；核对 `authorized_keys` |
| `denied: installation not allowed` 拉镜像失败 | `GHCR_PULL_TOKEN` 权限不足 | Token 需 `read:packages`；包可见性需允许 |
| 外网打不开 | 安全组未放行 80 | 阿里云控制台检查入方向 |
| 页面能开，接口失败 | backend 未 healthy 或 DB 密码错 | `docker compose logs backend` |
| 502 Bad Gateway | nginx 启动时 backend 未就绪（少见） | 看 backend healthcheck；`docker compose ps` |
| 刷新子路由 404 | nginx 缺 SPA 回退 | 确认 `try_files $uri $uri/ /index.html` |
| 磁盘满 | 旧镜像堆积 | `docker image prune -a`（慎用，会删未使用镜像） |
| CORS 报错 | `CORS_ORIGINS` 与访问地址不一致 | Secret 改成实际 `http://公网IP` 后重新部署 |

### 11.1 部署失败时看哪里

1. **GitHub Actions** 日志：build 失败看 Dockerfile/依赖；deploy 失败看 SSH、docker login、compose
2. **服务器**：`docker compose logs` 各服务
3. **GHCR Packages**：镜像是否 push 成功

### 11.2 一键体检（SSH 到 ECS 后执行）

```bash
cd /opt/crud-app
echo "========== 容器 ==========" && docker compose --env-file .env.deploy -f docker-compose.prod.yml ps
echo "========== 健康检查 ==========" && curl -s http://127.0.0.1/api/health && echo
echo "========== 磁盘 ==========" && df -h /
echo "========== Docker 占用 ==========" && docker system df
```

---

## 12. 服务器常用运维命令

以下命令均在 `/opt/crud-app` 下执行，统一加：

```bash
ENV="--env-file .env.deploy -f docker-compose.prod.yml"
```

### 12.1 查看状态与日志

```bash
docker compose $ENV ps
docker compose $ENV logs -f              # 全部服务
docker compose $ENV logs -f backend      # 仅后端
docker compose $ENV logs --tail=100 nginx
```

### 12.2 重启单个服务

```bash
docker compose $ENV restart backend
docker compose $ENV restart nginx
# mysql 慎重启；重启 backend 即可加载新代码镜像
```

### 12.3 手动拉取并更新（不通过 CI）

```bash
# 先编辑 .env.deploy 指定要拉的镜像 tag
docker compose $ENV pull
docker compose $ENV up -d
```

### 12.4 进入容器调试

```bash
docker compose $ENV exec backend sh
docker compose $ENV exec mysql mysql -u root -p
```

### 12.5 资源监控

```bash
docker stats                          # 各容器 CPU/内存实时占用
df -h /                               # 磁盘
free -h                               # 内存
```

---

## 13. 与裸机部署的对比

| 组件 | 裸机（HANDLE_DEPLOY） | Docker（本方案） |
| --- | --- | --- |
| 项目目录 | `/var/www/crud-app/` | `/opt/crud-app/` |
| 前端 | scp `dist/` 到磁盘 | 打进 nginx 镜像 |
| 后端 | venv + systemd | backend 容器 |
| Nginx | 系统级 `/etc/nginx/` | nginx 容器 + `docker/nginx.conf` |
| MySQL | apt 安装系统服务 | mysql 容器 + volume |
| 更新方式 | 手动 scp + restart | git push → Actions |
| 进程管理 | systemctl | docker compose |

**学习建议**：

1. 先通读 [HANDLE_DEPLOY.md](./HANDLE_DEPLOY.md)，理解 Nginx 反代、环境变量、健康检查各自干什么
2. 再在本地 `docker compose up` 跑通，对照本文第 3、4、5 节
3. 最后配 Secrets + push main，跟一遍 Actions 日志（第 8、9 节）

---

## 附录：信息速查

| 项 | 值 |
| --- | --- |
| 服务器部署目录 | `/opt/crud-app/` |
| Compose 文件 | `docker-compose.prod.yml` |
| 运行时环境文件 | `/opt/crud-app/.env.deploy`（CI 每次部署重写） |
| 对外端口 | 80（nginx 容器） |
| 数据库 | MySQL `crud_demo`，数据卷 `mysql_data` |
| 健康检查 | `GET /api/health` → `{"status":"ok"}` |
| 镜像仓库 | `ghcr.io/<owner>/<repo>-backend` / `-nginx` |
| 流水线文件 | `.github/workflows/ci-cd.yml` |

---

> **恭喜**：完成本文流程后，你已经实践了 **Docker 多容器编排**、**多阶段镜像构建**、**GHCR 私有仓库**、**GitHub Actions CI/CD** 和 **SSH 远程部署** 的完整链路。这些能力可以直接写进简历，并在面试中结合本项目讲解。
