# 部署总览笔记（新手向 · 越详细越好）

> 本笔记记录把「商品管理 CRUD 应用」部署到阿里云 ECS（Ubuntu）的完整思路与操作。
> 目标读者：第一次做部署、对 Linux/Nginx/systemd 还很陌生的自己。
> 核心原则：**先理解每块在干啥，再记命令**。命令只是配件，架构才是主线。

---

## 目录

1. [先建立心智模型](#1-先建立心智模型)
2. [整体架构图](#2-整体架构图)
3. [服务器上的关键角色](#3-服务器上的关键角色)
4. [一次完整部署的剧本（按顺序）](#4-一次完整部署的剧本按顺序)
5. [详细操作步骤](#5-详细操作步骤)
6. [关键命令详解](#6-关键命令详解命令--作用--属于哪块)
7. [一个请求的完整旅程](#7-一个请求的完整旅程)
8. [日常更新流程](#8-日常更新流程)
9. [常见问题排查](#9-常见问题排查)
10. [本项目专属信息速查](#10-本项目专属信息速查)

---

## 1. 先建立心智模型

一个网站 = **三样东西**：

| 组成 | 本地开发地址 | 作用 | 形态 |
| --- | --- | --- | --- |
| 前端 | `localhost:5173` | 给人看的页面（按钮、表格） | 打包后是一堆静态文件 `dist/` |
| 后端 | `localhost:8000` | 干活的（处理增删改查、连数据库） | 一个**一直运行的进程** |
| 数据库 | `localhost:3306` | 存数据 | MySQL 服务 |

**本地能跑**，是因为这三样都在你自己电脑上。
**要让别人访问**，就得把它们搬到一台「24 小时开机 + 有公网 IP」的电脑上 —— 这就是**云服务器（ECS）**。

云服务器本质上就是一台 Linux 电脑，没什么神秘，区别只是：**有公网 IP、一直开机**。

---

## 2. 整体架构图

```
用户浏览器
   │  http://8.136.47.107  (80 端口)
   ▼
┌─────────────────────────────────────────────────────────┐
│                    云服务器 ECS (Ubuntu)                   │
│                                                           │
│   🛡️ 阿里云安全组：必须放行 80 端口，否则外网进不来          │
│                                                           │
│   🚪 Nginx (监听 80)  ← 门卫 + 服务员                      │
│      ├── 访问 /        → 返回前端静态文件                   │
│      │                   /var/www/crud-app/frontend/dist  │
│      └── 访问 /api/... → 反向代理转发给后端                 │
│                              │                            │
│                              ▼                            │
│   ⚙️ 后端 uvicorn (127.0.0.1:8000)  ← 后厨                 │
│      运行 FastAPI 代码 /var/www/crud-app/backend           │
│                              │                            │
│                              ▼                            │
│   🗄️ MySQL (127.0.0.1:3306)  ← 仓库                       │
│      数据库 crud_demo，表 products                         │
│                                                           │
│   🤵 systemd  ← 管家：盯着后端进程，崩了自动重启、开机自启    │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 服务器上的关键角色

用「餐厅」比喻最好记：

| 部署角色 | 餐厅角色 | 一句话职责 |
| --- | --- | --- |
| 云服务器 ECS | 整个餐厅铺面 | 承载一切的机器 |
| **Nginx** | 门口的服务员 | 迎客、把网页端给客人、把 `/api` 点单转给后厨 |
| 前端 `dist/` | 菜单和餐具 | 摆出来给客人看的静态页面 |
| **后端 uvicorn** | 后厨 | 真正做菜（处理业务逻辑） |
| **systemd** | 店长 | 盯着后厨，厨师倒了立刻扶起来（重启、自启） |
| **MySQL** | 仓库 | 存食材（数据） |
| **chown** | 给后厨发钥匙 | 让后端进程有权限读写项目文件 |
| **安全组 80 端口** | 餐厅大门 | 决定外面能不能进来 |

**只有 3 个主角**：Nginx、systemd、权限(chown)。其余命令都是围着它们转的配件。

---

## 4. 一次完整部署的剧本（按顺序）

不用背命令，记这条**故事线**：

```
0. 装环境          → apt update/upgrade + 装 nginx/python/mysql-server（纯净版必做）
1. 建数据库        → 先有仓库放数据            (MySQL 建库)
2. 传代码上去      → 前端 dist、后端代码搬上服务器  (scp / Workbench 上传)
3. 让后端能连库    → 配 backend/.env（数据库密码、库名）
4. 装后端依赖      → python venv + pip install
5. 先手动试跑      → uvicorn 启动，curl 测 /api/health 是否 200
6. 交给管家常驻    → systemd（写 .service，enable + start）
7. 配门卫 Nginx    → 静态页 + /api 转发（写配置、ln -s、nginx -t、reload）
8. 开大门          → 阿里云安全组放行 80 端口
9. 浏览器访问      → http://公网IP，完成
```

---

## 5. 详细操作步骤

### 步骤 0：准备（纯净版服务器从零开始）

```bash
# SSH 登录服务器
ssh root@8.136.47.107

# 1. 刷新软件源清单（不装东西，只更新“商店目录”）
sudo apt update
# 2. 升级已装软件到最新（打安全补丁，新机器建议做一次）
sudo apt upgrade -y
# 3. 安装基础工具 + 数据库（纯净版必须自己装 mysql-server）
sudo apt install -y python3-venv python3-pip nginx git nano mysql-server
```

> `apt update` = 更新软件清单；`apt upgrade` = 按清单真正升级软件。先 update 再 upgrade。

安装完 MySQL 后，启动并做基础初始化：

```bash
sudo systemctl enable --now mysql      # 开机自启 + 立即启动
sudo mysql_secure_installation         # 设置 root 密码、删测试库等（按提示回车/y）
```

> 如果你的云镜像已自带 MySQL，可跳过安装，直接确认 `sudo systemctl status mysql` 是 running。

> 阿里云控制台 → 安全组 → 入方向规则 → 放行 **80 端口**（源 `0.0.0.0/0`）。很多人漏这步，导致本地 curl 通、外网打不开。

### 步骤 1：建数据库

```bash
mysql -u root -p        # 输入 root 密码
```

```sql
CREATE DATABASE crud_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- 可选：建专用账号（生产更安全，不用 root）
-- CREATE USER 'crud_user'@'localhost' IDENTIFIED BY '强密码';
-- GRANT ALL PRIVILEGES ON crud_demo.* TO 'crud_user'@'localhost';
-- FLUSH PRIVILEGES;
SHOW DATABASES;         -- 确认 crud_demo 已存在
EXIT;
```

> 表 `products` **不用手动建**，后端第一次启动时 `Base.metadata.create_all()` 会自动建。

### 步骤 2：上传代码

目录约定：`/var/www/crud-app/`

```
/var/www/crud-app/
├── backend/          # 后端源码
│   ├── app/          # main.py / crud.py / models.py / schemas.py / config.py / database.py
│   └── requirements.txt
└── frontend/
    └── dist/         # 前端打包产物
```

在**本地** Git Bash 用 scp 上传（不要在已登录服务器的窗口里执行）：

```bash
# 前端：先本地打包，再传 dist
cd C:/Users/95230/Desktop/mytest/frontend
npm run build
scp -r dist root@8.136.47.107:/var/www/crud-app/frontend/

# 后端：传 app 和 requirements.txt（不要传 .env / .venv / __pycache__）
scp -r C:/Users/95230/Desktop/mytest/backend/app root@8.136.47.107:/var/www/crud-app/backend/
scp C:/Users/95230/Desktop/mytest/backend/requirements.txt root@8.136.47.107:/var/www/crud-app/backend/
```

> **不要上传**：`.env`（含密码，服务器单独建）、`.venv/`（服务器自建）、`__pycache__/`（缓存）。

### 步骤 3：配置后端 .env

在服务器上：

```bash
cd /var/www/crud-app/backend
nano .env
```

内容（密码填**服务器 MySQL 的真实密码**，库名与实际一致）：

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_NAME=crud_demo
CORS_ORIGINS=http://8.136.47.107
```

保存：`Ctrl+O` → 回车 → `Ctrl+X`。

> 说明：因为前后端经 Nginx **同域**（都走公网 IP），本项目其实不依赖 CORS；但把 `CORS_ORIGINS` 写成公网 IP 比留 `localhost:5173` 更规范。

### 步骤 4：装依赖

```bash
cd /var/www/crud-app/backend
python3 -m venv .venv           # 建虚拟环境（隔离依赖）
source .venv/bin/activate       # 激活，命令行前面会出现 (.venv)
pip install -r requirements.txt
```

### 步骤 5：手动试跑（先验证能不能起）

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> 注意是 `app.main:app`：`app` 是文件夹，`main` 是 main.py，`:app` 是里面的 FastAPI 对象。
> 常见错误 `Could not import module "main"` 就是写成了 `main:app`。

**另开一个终端**测试：

```bash
curl http://127.0.0.1:8000/api/health     # 应返回 {"status":"ok"}
```

看到 `200 OK` 就说明后端 + 数据库都通了。回第一个终端 `Ctrl+C` 停掉，进入常驻。

### 步骤 6：systemd 让后端常驻

手动跑一关终端就停，交给 systemd 才能 7×24 运行。

```bash
sudo nano /etc/systemd/system/crud-backend.service
```

粘贴（路径按实际 `crud-app`）：

```ini
[Unit]
Description=CRUD Demo FastAPI Backend
After=network.target mysql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/crud-app/backend
Environment="PATH=/var/www/crud-app/backend/.venv/bin"
ExecStart=/var/www/crud-app/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo chown -R www-data:www-data /var/www/crud-app   # 把项目交给后端运行用户
sudo systemctl daemon-reload                        # 让 systemd 重新读配置
sudo systemctl enable --now crud-backend            # 开机自启 + 立即启动
sudo systemctl status crud-backend                  # 看到 active (running) 即成功
```

### 步骤 7：配置 Nginx

```bash
sudo nano /etc/nginx/sites-available/crud-app
```

粘贴：

```nginx
server {
    listen 80;
    server_name _;                                  # 有域名就填域名

    root /var/www/crud-app/frontend/dist;           # 前端静态文件目录
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;           # 前端路由回退，刷新子页面不 404
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;           # /api 转发给后端
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用：

```bash
sudo ln -s /etc/nginx/sites-available/crud-app /etc/nginx/sites-enabled/   # 软链接=启用站点
sudo rm -f /etc/nginx/sites-enabled/default                               # 去掉默认站点，避免冲突
sudo nginx -t                                                             # 检查配置语法
sudo systemctl reload nginx                                               # 平滑生效
```

### 步骤 8：浏览器访问

打开 **http://8.136.47.107**，应看到商品管理页面，并可增删改查。

> 打不开先查：安全组是否放行 80？后端 `systemctl status crud-backend` 是否 running？

---

## 6. 关键命令详解（命令 → 作用 → 属于哪块）

| 命令 | 大白话作用 | 属于架构哪块 |
| --- | --- | --- |
| `ssh root@IP` | 远程登录服务器 | 连接 |
| `scp -r 本地 远程` | 把文件传到服务器（相当于上传） | 传代码 |
| `nano 文件` | 命令行里的“记事本”，编辑文件 | 辅助工具 |
| `python3 -m venv .venv` | 建虚拟环境，隔离 Python 依赖 | 后端 |
| `source .venv/bin/activate` | 激活虚拟环境 | 后端 |
| `pip install -r requirements.txt` | 装后端依赖 | 后端 |
| `uvicorn app.main:app` | 运行 FastAPI 后端 | 后端进程 |
| `curl 网址` | 命令行发请求，测接口通不通 | 验证 |
| **`chown -R www-data:www-data`** | 把文件“主人”设成后端运行用户，给权限 | 📁 文件权限 |
| **`ln -s A B`** | 建软链接（快捷方式），把站点配置“摆上菜单”启用 | 🚪 Nginx |
| **`systemctl daemon-reload`** | 让 systemd 重新读 `.service` 配置 | 🤵 systemd |
| **`systemctl enable --now 服务`** | 开机自启 + 立即启动 | 🤵 systemd |
| **`systemctl status 服务`** | 看服务活着没 | 🤵 systemd |
| **`nginx -t`** | 检查 Nginx 配置有没有写错 | 🚪 Nginx |
| **`systemctl reload nginx`** | 让 Nginx 加载新配置（用户不断线） | 🚪 Nginx |

### 为什么配置文件放在那些固定路径？

- `/etc/systemd/system/xxx.service`：systemd 只在固定目录找服务文件，放这里才能被 `systemctl` 管理。
- `/etc/nginx/sites-available/`：放**所有**站点配置（仓库）。
- `/etc/nginx/sites-enabled/`：放**已启用**的（用软链接指过去）。想停用某站点删软链接即可，原配置还在。

---

## 7. 一个请求的完整旅程

以「用户新增一个商品」为例：

```
1. 浏览器打开 http://8.136.47.107
2. Nginx 收到 → 返回 dist/index.html（页面出现）
3. 用户点“新增” → 浏览器发 POST /api/products
4. Nginx 看到 /api → 转发给 127.0.0.1:8000（后端）
5. 后端 FastAPI 处理 → 向 MySQL 执行 INSERT
6. MySQL 保存成功 → 返回后端
7. 后端返回结果 → Nginx → 浏览器
8. 页面显示新商品 ✅
```

---

## 8. 日常更新流程

改了代码后如何更新线上：

```bash
# —— 改了后端代码 ——
# 1. 本地改完，scp 传上去（或 git pull）
scp -r C:/Users/95230/Desktop/mytest/backend/app root@8.136.47.107:/var/www/crud-app/backend/
# 2. 依赖有变化才需要重装
#    source /var/www/crud-app/backend/.venv/bin/activate && pip install -r requirements.txt
# 3. 重启后端
sudo systemctl restart crud-backend

# —— 改了前端代码 ——
# 1. 本地重新打包
cd C:/Users/95230/Desktop/mytest/frontend && npm run build
# 2. 传 dist 覆盖
scp -r dist root@8.136.47.107:/var/www/crud-app/frontend/
# 3. 前端是静态文件，一般无需重启；如改了 nginx 配置才 reload
sudo systemctl reload nginx
```

记忆口诀：**改后端 → restart 后端；改前端 → 传 dist（必要时 reload nginx）**。

---

## 9. 常见问题排查

| 现象 | 可能原因 | 排查/解决 |
| --- | --- | --- |
| 外网打不开，本地 curl 正常 | 安全组没放行 80 | 阿里云控制台放行 80 端口 |
| 页面能开，但操作报错/加载失败 | 后端没起来 或 `/api` 代理没配好 | `systemctl status crud-backend`；查 Nginx 配置 |
| **502 Bad Gateway** | 后端进程挂了 / 端口不是 8000 | `journalctl -u crud-backend -f` 看日志 |
| 后端起不来，日志报数据库错误 | `.env` 账号/密码/库名不对 | 核对 `.env`；确认库存在、密码对 |
| `Could not import module "main"` | 启动命令写错 | 用 `uvicorn app.main:app`，不是 `main:app` |
| 前端刷新子路由 404 | Nginx 缺 `try_files` 回退 | 确认 `try_files $uri $uri/ /index.html;` |
| 关了终端后端就停 | 还在手动前台跑 | 改用 systemd 常驻 |

常用查日志命令：

```bash
sudo systemctl status crud-backend      # 服务状态
sudo journalctl -u crud-backend -f      # 实时后端日志
sudo tail -f /var/log/nginx/error.log   # Nginx 错误日志
```

---

## 10. 本项目专属信息速查

| 项 | 值 |
| --- | --- |
| 公网 IP | `8.136.47.107` |
| 项目根目录 | `/var/www/crud-app/` |
| 后端目录 | `/var/www/crud-app/backend/` |
| 前端目录 | `/var/www/crud-app/frontend/dist/` |
| 后端端口 | `127.0.0.1:8000`（只对内，Nginx 反代） |
| 数据库 | MySQL `crud_demo`，表 `products` |
| systemd 服务名 | `crud-backend` |
| Nginx 站点配置 | `/etc/nginx/sites-available/crud-app` |
| 健康检查 | `curl http://127.0.0.1:8000/api/health` → `{"status":"ok"}` |

### 一分钟自检清单

```bash
sudo systemctl status crud-backend                 # 后端 running？
curl http://127.0.0.1:8000/api/health              # 返回 ok？
sudo nginx -t                                      # 配置 ok？
sudo systemctl status nginx                        # nginx running？
# 浏览器打开 http://8.136.47.107 能增删改查？
```

---

> 记住：部署不是背命令，而是搭一条链路
> **浏览器 → Nginx(门卫) → 前端dist(菜单) / 后端uvicorn(后厨) → MySQL(仓库)**，
> systemd(店长) 看着后厨，chown 给后厨钥匙，安全组是大门。
> 理解了每个角色，命令自然各归各位。
