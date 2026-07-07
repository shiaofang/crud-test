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
10. [服务器日常监控与常用命令](#10-服务器日常监控与常用命令)
11. [本项目专属信息速查](#11-本项目专属信息速查)

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
| **`systemctl start/stop/restart 服务`** | 启动 / 停止 / 重启服务 | 🤵 systemd |
| **`systemctl enable --now 服务`** | 开机自启 + 立即启动 | 🤵 systemd |
| **`systemctl status 服务`** | 看服务活着没 | 🤵 systemd |
| **`nginx -t`** | 检查 Nginx 配置有没有写错 | 🚪 Nginx |
| **`systemctl reload nginx`** | 让 Nginx 加载新配置（用户不断线） | 🚪 Nginx |

> `systemctl` 完整用法见 [§10.8 systemd 服务管理](#108-systemd-服务管理systemctl-完整指南)。

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

## 10. 服务器日常监控与常用命令

> SSH 登录阿里云 ECS 后，Ubuntu 会在欢迎信息（MOTD）里自动显示一行摘要，例如：
> `System load: 0.05` · `Usage of /: 10.5% of 39.01GB` · `Memory usage: 29%` · `Swap usage: 0%`
>
> 这些数字分别对应 **负载、磁盘、内存、交换分区**。下面教你用命令自己查，比只看登录提示更详细、更可控。

### 10.1 先搞懂：你在看什么

| 指标 | 大白话 | 大致健康标准（小项目） |
| --- | --- | --- |
| **CPU 负载** | 排队等 CPU 干活的任务数 | 长期 < CPU 核数（如 2 核机器负载 < 2） |
| **内存** | 程序运行时占用的 RAM | 使用率 < 80% 较安心；接近 100% 可能 OOM 杀进程 |
| **磁盘** | 硬盘还剩多少空间 | 根分区 `/` 使用率 < 80%；日志、数据库会持续增长 |
| **Swap** | 内存不够时拿硬盘顶一下 | 长期 > 0% 说明内存偏紧，要关注 |
| **进程数** | 当前运行的程序个数 | 突然暴涨要查是不是被挖矿或异常脚本 |

---

### 10.2 内存：`free -h`

```bash
free -h
```

`-h` = **human-readable**，把字节换算成 `GiB` / `MiB`，人眼友好。

**典型输出：**

```
               total        used        free      shared  buff/cache   available
Mem:           3.5Gi       1.0Gi       1.2Gi        20Mi       1.3Gi       2.2Gi
Swap:             0B          0B          0B
```

**各列含义：**

| 列 | 含义 |
| --- | --- |
| `total` | 物理内存总量 |
| `used` | 已被进程占用的部分 |
| `free` | 完全空闲、没人用的 |
| `buff/cache` | 系统用来做磁盘缓存的（可回收，不算真正“用光”） |
| **`available`** | **最重要**：估算“还能给新程序用多少”，比看 `free` 更准 |
| `Swap` | 交换分区；`used` 长期不为 0 说明内存紧张 |

**常用变体：**

```bash
free -h -s 5          # 每 5 秒刷新一次（Ctrl+C 退出）
free -m               # 以 MB 为单位显示
cat /proc/meminfo     # 更底层的原始数据，排查时用
```

**和本项目的关系：** 后端 uvicorn（`--workers 2`）、MySQL、Nginx 都占内存。若 `available` 只剩几百 MB，考虑减 worker 数或升级 ECS 规格。

---

### 10.3 磁盘空间：`df -h`

```bash
df -h
```

> 常见笔误：没有 `df -f` 这个常用选项；要看磁盘请用 **`df -h`**（human-readable）。  
> `-h` 和 `free -h` 里的 `-h` 一样，都是“人类可读单位”。

**典型输出：**

```
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda3        40G  4.1G   34G  11% /
tmpfs           1.8G     0  1.8G   0% /dev/shm
```

**各列含义：**

| 列 | 含义 |
| --- | --- |
| `Filesystem` | 分区设备名（云盘多为 `/dev/vda*`） |
| `Size` | 分区总容量 |
| `Used` / `Avail` | 已用 / 剩余 |
| **`Use%`** | **使用率百分比**，盯紧 `Mounted on` 为 `/` 的那一行 |
| `Mounted on` | 挂载点；`/` 是系统根分区，最重要 |

**常用变体：**

```bash
df -h /                    # 只看根分区
df -h /var/www/crud-app    # 只看项目目录所在分区
df -i                      # 看 inode 使用率（小文件极多时会 inode 满但空间还有）
df -Th                     # 同时显示文件系统类型（ext4、xfs 等）
```

**查“谁占了大头”——配合 `du`：**

```bash
du -sh /var/www/crud-app/*     # 看项目各子目录占用
du -sh /var/log/*              # 日志是否膨胀
du -h --max-depth=1 /var/www   # 一层子目录汇总
```

| 命令 | 作用 |
| --- | --- |
| `du -s` | summarize，只输出总计 |
| `du -h` | 人类可读单位 |
| `du --max-depth=1` | 只展开一层，避免刷屏 |

**告警线：** 根分区 `Use%` 超过 **85%** 要清理或扩容；MySQL 数据、Nginx 日志、`journalctl` 日志是常见增长点。

---

### 10.4 CPU 与负载：`uptime`、`top`、`htop`

**快速看负载：**

```bash
uptime
```

输出示例：`17:58:52 up 3 days, load average: 0.05, 0.03, 0.01`

| 数字 | 含义 |
| --- | --- |
| 第 1 个 | 过去 **1 分钟** 平均负载 |
| 第 2 个 | 过去 **5 分钟** |
| 第 3 个 | 过去 **15 分钟** |

负载 ≈ “等 CPU 的任务队列长度”。2 核 CPU 机器，负载长期 > 2 说明 CPU 偏忙。

**交互式实时监控：**

```bash
top                  # 系统自带，按 q 退出
htop                 # 更直观（需 apt install htop）
```

`top` 里常用按键：

| 键 | 作用 |
| --- | --- |
| `1` | 展开每个 CPU 核心的使用率 |
| `M` | 按内存占用排序 |
| `P` | 按 CPU 占用排序 |
| `c` | 显示完整命令行 |
| `q` | 退出 |

**看 CPU 硬件信息：**

```bash
nproc                # CPU 逻辑核数
lscpu                # 型号、核数、架构等详情
```

---

### 10.5 进程：`ps`

```bash
ps aux | head -20                    # 看前 20 个进程
ps aux | grep uvicorn                # 找后端进程
ps aux | grep mysql                  # 找数据库进程
ps aux --sort=-%mem | head -10       # 内存占用 Top 10
ps aux --sort=-%cpu | head -10       # CPU 占用 Top 10
```

`ps aux` 各列简记：`USER` 运行用户、`%CPU`/`%MEM` 占用、`COMMAND` 命令。

**杀进程（慎用）：**

```bash
kill PID              # 温和结束
kill -9 PID           # 强制结束（先尽量 systemctl stop）
```

本项目后端应通过 `sudo systemctl restart crud-backend` 重启，不要随手 `kill -9` uvicorn。

---

### 10.6 磁盘与块设备：`lsblk`、`fdisk`

```bash
lsblk                 # 树状看磁盘、分区、挂载点
lsblk -f              # 附带文件系统类型、UUID
sudo fdisk -l         # 列出分区表（只读查看）
```

云服务器常见：`/dev/vda` 整块盘 → `vda1` boot → `vda3` 挂到 `/`。

---

### 10.7 网络：`ss`、`curl`、`ping`

```bash
ss -tlnp              # 看哪些端口在监听（t=TCP, l=监听, n=数字端口, p=进程）
ss -tlnp | grep 8000  # 确认后端是否在 8000 监听
ss -tlnp | grep 80    # 确认 Nginx 是否在 80 监听
curl -I http://127.0.0.1:8000/api/health   # 测本机 HTTP 响应头
ping -c 4 8.8.8.8     # 测外网连通（-c 4 发 4 个包后停）
```

| 现象 | 可能原因 |
| --- | --- |
| `8000` 没有监听 | 后端没启动或启动失败 |
| `80` 没有监听 | Nginx 没起来 |
| 本机 curl 通、外网不通 | 安全组或防火墙 |

---

### 10.8 systemd 服务管理：`systemctl` 完整指南

> **systemd** 是 Linux 的“服务管家”，**systemctl** 是你跟它对话的命令行工具。
> 部署后，后端、Nginx、MySQL 都应交给 systemd 管，而不是手动前台跑或 `kill` 进程。

#### 本项目要关心的三个服务

| 服务名 | 是什么 | 配置文件位置 |
| --- | --- | --- |
| `crud-backend` | 自建 FastAPI 后端 | `/etc/systemd/system/crud-backend.service` |
| `nginx` | 门卫 / 反向代理 | `/lib/systemd/system/nginx.service`（系统自带） |
| `mysql` | 数据库 | `/lib/systemd/system/mysql.service`（系统自带） |

以下示例把 `服务名` 换成上表中的名字即可；**改 `.service` 文件后几乎都要先 `daemon-reload`**。

---

#### 10.8.1 启动 / 停止 / 重启（最常用）

| 命令 | 作用 | 典型场景 |
| --- | --- | --- |
| `sudo systemctl start 服务名` | **启动**（若已在运行则一般无操作） | 第一次部署完、或 stop 之后重新拉起 |
| `sudo systemctl stop 服务名` | **停止**（进程结束，端口释放） | 维护数据库、临时下线后端 |
| `sudo systemctl restart 服务名` | **先停再启**（会断一下连接） | **改了后端代码**后让新代码生效 |
| `sudo systemctl reload 服务名` | **热加载配置**（进程不退出） | Nginx 改配置后平滑生效 |
| `sudo systemctl try-restart 服务名` | 仅在**正在运行**时才 restart | 脚本里用，避免没跑时误启动 |

```bash
# —— 后端 ——
sudo systemctl start crud-backend       # 启动后端
sudo systemctl stop crud-backend        # 停止后端（网站 /api 会挂）
sudo systemctl restart crud-backend     # 改代码后最常用 ✅

# —— Nginx ——
sudo systemctl start nginx
sudo systemctl stop nginx               # 整站不可访问
sudo systemctl restart nginx            # 硬重启（短暂断线）
sudo systemctl reload nginx             # 改 nginx 配置后优先用这个 ✅

# —— MySQL ——
sudo systemctl start mysql
sudo systemctl stop mysql               # 停库前最好先停后端
sudo systemctl restart mysql            # 改 my.cnf 等配置后
```

**`restart` 和 `reload` 怎么选？**

| 情况 | 用哪个 |
| --- | --- |
| 改了 Python 代码、`requirements.txt`、`.env` | `restart crud-backend` |
| 改了 `crud-backend.service` 单元文件 | `daemon-reload` 然后 `restart crud-backend` |
| 改了 Nginx 站点配置 | 先 `nginx -t`，再 `reload nginx` |
| 服务卡死、reload 无效 | `restart` |

---

#### 10.8.2 开机自启：`enable` / `disable`

| 命令 | 作用 |
| --- | --- |
| `sudo systemctl enable 服务名` | 写入开机自启（**此刻不一定在运行**） |
| `sudo systemctl disable 服务名` | 取消开机自启（**不会停止当前正在跑的服务**） |
| `sudo systemctl enable --now 服务名` | **开机自启 + 立刻启动**（部署时一步到位）✅ |
| `sudo systemctl disable --now 服务名` | 取消自启 + 立刻停止 |

```bash
sudo systemctl enable --now crud-backend    # 部署第 6 步
sudo systemctl enable --now mysql             # 装完数据库后
sudo systemctl enable --now nginx             # 一般安装 nginx 时已自动 enable

sudo systemctl is-enabled crud-backend        # 输出 enabled / disabled
```

---

#### 10.8.3 查看状态：`status` 与轻量查询

```bash
sudo systemctl status crud-backend      # 最详细：含最近几行日志
sudo systemctl status nginx
sudo systemctl status mysql
```

**`status` 里要会看的几行：**

| 显示 | 含义 |
| --- | --- |
| `Active: active (running)` | ✅ 正常运行 |
| `Active: inactive (dead)` | 已停止 |
| `Active: failed` | 启动失败，要看下面日志 |
| `Loaded: ... enabled` | 已设开机自启 |
| `Loaded: ... disabled` | 不会开机自启 |
| `Main PID: 12345` | 主进程号（排查、对应 `ps`） |

**只要一个词结果时（适合脚本 / 体检）：**

```bash
systemctl is-active crud-backend     # active / inactive / failed
systemctl is-enabled crud-backend    # enabled / disabled
systemctl is-failed crud-backend     # failed 或 active（没失败）
```

```bash
# 列出正在跑的服务（可加过滤）
systemctl list-units --type=service --state=running
systemctl list-units --type=service | grep -E 'crud|nginx|mysql'

# 列出所有服务单元及是否开机自启
systemctl list-unit-files --type=service | grep -E 'crud|nginx|mysql'
```

---

#### 10.8.4 改完配置必做：`daemon-reload`

只要你**新建或修改**了 `/etc/systemd/system/*.service`，必须：

```bash
sudo systemctl daemon-reload              # 让 systemd 重新读磁盘上的单元文件
sudo systemctl restart crud-backend       # 再重启服务，新配置才生效
```

漏掉 `daemon-reload` 的典型症状：你明明改了 `.service`，`status` 里还是旧的 `ExecStart` 路径。

**查看单元文件实际内容：**

```bash
systemctl cat crud-backend                # 打印当前生效的 unit 配置
systemctl show crud-backend               # 更多属性（环境变量、PID、路径等）
systemctl show crud-backend -p ExecStart  # 只看启动命令
```

---

#### 10.8.5 失败与排错

```bash
sudo systemctl reset-failed                    # 清除所有 failed 标记（排错后清状态）
sudo systemctl reset-failed crud-backend         # 只清某一个

sudo journalctl -u crud-backend -n 80 --no-pager # 看最近 80 行日志（status 装不下时用这个）
sudo journalctl -u crud-backend -f               # 实时跟日志（启动失败时边 start 边看）
```

**推荐排错顺序：**

```
1. systemctl status 服务名          → 看是不是 failed、最后一行报错
2. journalctl -u 服务名 -n 50       → 看完整错误栈
3. 修配置 / 代码 / 权限
4. daemon-reload（若改了 .service）
5. restart 服务名
6. reset-failed（可选，清红字状态）
```

---

#### 10.8.6 进阶（知道即可）

| 命令 | 作用 | 备注 |
| --- | --- | --- |
| `sudo systemctl mask 服务名` | 彻底禁止启动（连手动 start 也不行） | 比 disable 更狠，一般别对 mysql/nginx 乱用 |
| `sudo systemctl unmask 服务名` | 解除 mask | |
| `sudo systemctl kill 服务名` | 向服务主进程发信号 | 优先用 `stop`，别替代日常运维 |
| `systemctl list-dependencies crud-backend` | 看依赖树（After= 等） | 理解启动顺序 |

---

#### 10.8.7 本项目高频场景速查

| 你想做的事 | 命令 |
| --- | --- |
| 部署完第一次拉起后端 | `sudo systemctl enable --now crud-backend` |
| 本地 scp 了新后端代码 | `sudo systemctl restart crud-backend` |
| 改了 `crud-backend.service` | `sudo systemctl daemon-reload && sudo systemctl restart crud-backend` |
| 改了 Nginx 站点配置 | `sudo nginx -t && sudo systemctl reload nginx` |
| 看后端为什么 502 | `sudo systemctl status crud-backend` + `sudo journalctl -u crud-backend -f` |
| 临时停站维护 | `sudo systemctl stop crud-backend`（或 stop nginx） |
| 服务器重启后确认都起来了 | `systemctl is-active crud-backend nginx mysql` |
| 查 8000 是否在监听 | `ss -tlnp \| grep 8000`（配合 status 使用） |

**维护时推荐停服顺序：** 先 `stop crud-backend` → 再动 MySQL / 改库；改完再 `start mysql` → `start crud-backend`。避免后端连着一半的数据库操作。

---

#### 10.8.8 `systemctl` 命令总表

| 命令 | 一句话 |
| --- | --- |
| `start` | 启动 |
| `stop` | 停止 |
| `restart` | 重启（断一下） |
| `reload` | 热加载配置 |
| `try-restart` | 在跑才重启 |
| `enable` | 开机自启 |
| `disable` | 取消开机自启 |
| `enable --now` | 自启 + 立即启动 |
| `disable --now` | 取消自启 + 立即停止 |
| `status` | 详细状态 + 少量日志 |
| `is-active` | 是否在运行 |
| `is-enabled` | 是否开机自启 |
| `is-failed` | 是否处于失败状态 |
| `daemon-reload` | 重新加载 unit 文件 |
| `reset-failed` | 清除失败标记 |
| `cat` | 查看 unit 文件内容 |
| `show` | 查看服务属性 |
| `list-units` | 列出单元（可按状态过滤） |
| `list-unit-files` | 列出单元文件及 enable 状态 |
| `mask` / `unmask` | 禁止 / 恢复启动 |
| `kill` | 向进程发信号 |

---

### 10.9 日志：`journalctl`、`tail`

```bash
# systemd 管理的服务日志（后端）
sudo journalctl -u crud-backend -n 50        # 最近 50 行
sudo journalctl -u crud-backend -f           # 实时跟踪（像 tail -f）
sudo journalctl -u crud-backend --since today
sudo journalctl -u crud-backend --since "1 hour ago"

# 文件型日志
sudo tail -n 100 /var/log/nginx/access.log   # Nginx 访问日志
sudo tail -n 100 /var/log/nginx/error.log    # Nginx 错误日志
sudo tail -f /var/log/nginx/error.log        # 实时盯错误
```

| 场景 | 优先看 |
| --- | --- |
| 后端 502 / 起不来 | `journalctl -u crud-backend -f` |
| 页面 404 / 静态资源 | Nginx `error.log` |
| 接口慢、谁访问多 | Nginx `access.log` |

---

### 10.10 系统信息一览

```bash
uname -a              # 内核版本、架构
hostname              # 主机名（阿里云类似 iZbp1380dtwgpyssuhoxw6Z）
whoami                # 当前用户（部署时常为 root）
id                    # 用户 UID/GID、所属组
date                  # 系统时间（时区不对会导致证书、日志混乱）
timedatectl           # 时区、NTP 同步状态
cat /etc/os-release   # Ubuntu 版本号
```

---

### 10.11 文件与目录常用操作（复习）

```bash
ls -lah               # 列表，含隐藏文件、人类可读大小
cd /var/www/crud-app  # 进入目录
pwd                   # 当前路径
cat 文件              # 查看全文（小文件）
less 文件             # 分页查看（大文件，q 退出）
head -n 20 文件       # 看前 20 行
tail -n 20 文件       # 看后 20 行
nano 文件             # 编辑
cp -r 源 目标         # 复制
mv 源 目标            # 移动/重命名
rm 文件               # 删除文件（谨慎！）
rm -rf 目录           # 递归删除目录（极其谨慎！）
chmod 644 文件        # 改权限
chown user:group 文件 # 改属主（部署见 chown www-data）
```

---

### 10.12 登录后「一分钟体检」脚本（可复制执行）

SSH 登录后，把下面整段贴进终端，快速扫一遍机器状态：

```bash
echo "========== 系统 =========="
uptime
echo ""
echo "========== 内存 (free -h) =========="
free -h
echo ""
echo "========== 磁盘 (df -h) =========="
df -h /
echo ""
echo "========== 项目目录占用 =========="
du -sh /var/www/crud-app/* 2>/dev/null
echo ""
echo "========== 核心服务 =========="
systemctl is-active crud-backend nginx mysql
echo ""
echo "========== 端口监听 =========="
ss -tlnp | grep -E ':80|:8000|:3306'
echo ""
echo "========== 健康检查 =========="
curl -s http://127.0.0.1:8000/api/health
echo ""
```

期望结果：`crud-backend` / `nginx` / `mysql` 均为 `active`；`8000`、`80` 有监听；健康检查返回 `{"status":"ok"}`。

---

### 10.13 命令速查表

| 命令 | 作用 | 记忆口诀 |
| --- | --- | --- |
| `free -h` | 内存与 Swap | **free** 看空闲 |
| `df -h` | 磁盘分区使用率 | **df** = disk free |
| `du -sh 路径` | 某目录占多大 | **du** = disk usage |
| `uptime` | 运行时间与负载 | 三个负载数字 |
| `top` / `htop` | 实时资源监控 | 任务管理器 |
| `ps aux` | 进程快照 | 配合 grep |
| `ss -tlnp` | 端口与进程 | 代替 netstat |
| `systemctl start/stop/restart` | 启停服务 | 改代码用 restart |
| `systemctl enable --now` | 自启并立即启动 | 部署必做 |
| `systemctl status` | 服务详细状态 | 部署三件套 |
| `systemctl is-active` | 是否在运行 | 脚本体检用 |
| `systemctl daemon-reload` | 重读 .service 文件 | 改 unit 后必做 |
| `systemctl reload nginx` | Nginx 热加载配置 | 不断线 |
| `journalctl -u 服务 -f` | 服务日志 | 排错第一工具 |
| `tail -f 日志文件` | 盯文件日志 | Nginx 错误在这 |

---

## 11. 本项目专属信息速查

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

> 更完整的系统体检见 [§10.12 登录后一分钟体检](#1012-登录后一分钟体检脚本可复制执行)。

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
