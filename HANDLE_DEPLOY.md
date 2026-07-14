# 裸机手动部署参考手册

> **说明**：生产环境已改用 CI/CD + Docker 自动部署（见 `.github/workflows/ci-cd.yml`）。  
> 本文档保留 **Ubuntu 裸机部署** 的完整流程，供学习参考。

---

## 目录

1. [部署流程概览](#1-部署流程概览)
2. [详细步骤](#2-详细步骤)
3. [日常更新](#3-日常更新)
4. [常见问题排查](#4-常见问题排查)
5. [服务器常用命令](#5-服务器常用命令)
6. [项目信息速查](#6-项目信息速查)

---

## 1. 部署流程概览

```
0. 装环境     → apt update/upgrade + nginx/python/mysql
1. 建数据库   → CREATE DATABASE crud_demo
2. 传代码     → scp 前端 dist + 后端 app
3. 配 .env    → 数据库密码、CORS
4. 装依赖     → python venv + pip install
5. 试跑       → uvicorn 手动启动，curl 测 /api/health
6. systemd    → 写 .service，enable + start
7. Nginx      → 静态页 + /api 反代，nginx -t + reload
8. 安全组     → 阿里云放行 80 端口
9. 验证       → 浏览器访问 http://公网IP
```

**目录结构**：

```
/var/www/crud-app/
├── backend/
│   ├── app/                # Python 包（含 __init__.py）
│   ├── .env
│   ├── .venv/
│   └── requirements.txt
└── frontend/
    └── dist/
```

---

## 2. 详细步骤

### 2.1 安装环境

```bash
# SSH 远程登录服务器；-p 可指定端口（默认 22）
ssh root@<你的公网IP>

# apt update：刷新软件源清单（不安装，只更新"商店目录"）
# apt upgrade -y：按清单升级已装软件；-y 自动确认，不打断
# 顺序：先 update 再 upgrade
sudo apt update && sudo apt upgrade -y

# 安装部署所需软件包
# python3-venv：创建 Python 虚拟环境
# python3-pip：Python 包管理器
# nginx：Web 服务器 / 反向代理
# mysql-server：数据库
# git / nano：版本控制 & 命令行编辑器
sudo apt install -y python3-venv python3-pip nginx git nano mysql-server

# enable：设置开机自启；--now：同时立即启动
sudo systemctl enable --now mysql

# 交互式安全初始化：设 root 密码、删匿名用户、禁远程 root 登录等
sudo mysql_secure_installation
```

| 命令 | 作用 |
| --- | --- |
| `ssh user@IP` | 远程登录 Linux 服务器 |
| `apt update` | 更新软件包索引 |
| `apt upgrade -y` | 升级已安装软件 |
| `apt install -y 包名` | 安装指定软件 |
| `systemctl enable --now mysql` | MySQL 开机自启并立即启动 |

> 阿里云控制台 → 安全组 → 入方向 → 放行 **80** 端口（HTTP）。漏这步会导致本机 curl 通、外网打不开。

---

### 2.2 建数据库

```bash
# -u root：用 root 用户登录；-p：提示输入密码（不会显示在屏幕上）
mysql -u root -p
```

```sql
-- utf8mb4：支持 emoji 等 4 字节字符；比 utf8 更完整
CREATE DATABASE crud_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 确认库已创建
SHOW DATABASES;

-- 退出 MySQL 客户端
EXIT;
```

> 表 `products` 由后端 `Base.metadata.create_all()` 在首次启动时自动创建，无需手动建表。

---

### 2.3 上传代码

**本地**执行（Git Bash，不要在已 SSH 登录的服务器窗口里跑 scp）：

```bash
# —— 前端 ——
cd C:/path/to/crud-app/frontend
npm run build                    # 打包生成 dist/ 静态文件
# scp -r：递归复制整个目录
# 格式：scp -r 本地路径 用户@IP:远程路径
scp -r dist root@<你的公网IP>:/var/www/crud-app/frontend/

# —— 后端 ——
# 只传 app/ 和 requirements.txt
# 不要传：.env（含密码）、.venv/（服务器自建）、__pycache__/（缓存）
scp -r C:/path/to/crud-app/backend/app root@<你的公网IP>:/var/www/crud-app/backend/
scp C:/path/to/crud-app/backend/requirements.txt root@<你的公网IP>:/var/www/crud-app/backend/
```

| 命令 | 作用 |
| --- | --- |
| `npm run build` | 前端打包，产出 `dist/` |
| `scp -r 本地 远程` | 通过 SSH 上传文件/目录到服务器 |
| `scp 单文件 远程` | 上传单个文件 |

---

### 2.4 配置 .env

```bash
cd /var/www/crud-app/backend
nano .env          # 命令行编辑器；Ctrl+O 保存，Ctrl+X 退出
```

```env
DB_HOST=127.0.0.1              # 数据库地址；裸机部署 MySQL 在本机
DB_PORT=3306                   # MySQL 默认端口
DB_USER=root                   # 数据库用户名
DB_PASSWORD=你的MySQL密码       # 填 mysql_secure_installation 设的密码
DB_NAME=crud_demo              # 库名，须与 CREATE DATABASE 一致
CORS_ORIGINS=http://<你的公网IP>  # 允许跨域的来源；同域经 Nginx 时可不改
```

---

### 2.5 安装依赖 & 试跑

```bash
cd /var/www/crud-app/backend

# 在当前目录创建 .venv 虚拟环境，隔离项目依赖
python3 -m venv .venv

# 激活虚拟环境；成功后命令行前会出现 (.venv)
# 每次新开终端装依赖/手动跑都要先 activate
source .venv/bin/activate

# 按 requirements.txt 安装后端依赖
pip install -r requirements.txt

# 前台启动 FastAPI
# app.main:app → app 是 Python 包（含 __init__.py），main 是 main.py，:app 是 FastAPI 实例
# --host 127.0.0.1：只监听本机，外网经 Nginx 反代访问
# --port 8000：后端端口
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**另开终端**验证：

```bash
# curl：命令行发 HTTP 请求
# 期望返回 {"status":"ok"} 且 HTTP 200
curl http://127.0.0.1:8000/api/health
```

> 验证通过后，回到 uvicorn 终端 `Ctrl+C` 停止，再交给 systemd 常驻（关终端不会停）。

| 命令 | 作用 |
| --- | --- |
| `python3 -m venv .venv` | 创建 Python 虚拟环境 |
| `source .venv/bin/activate` | 激活虚拟环境 |
| `pip install -r requirements.txt` | 安装依赖列表 |
| `uvicorn app.main:app` | 启动 FastAPI（**不是** `main:app`） |
| `curl URL` | 测试 HTTP 接口是否通 |

---

### 2.6 systemd 常驻

```bash
# systemd 单元文件必须放在此固定目录，systemctl 才能识别
sudo nano /etc/systemd/system/crud-backend.service
```

```ini
[Unit]
Description=CRUD Demo FastAPI Backend
After=network.target mysql.service    # 等网络和 MySQL 就绪后再启动

[Service]
Type=simple                           # 简单前台进程类型
User=www-data                         # 以 www-data 用户运行（与 Nginx 同用户）
Group=www-data
WorkingDirectory=/var/www/crud-app/backend   # 工作目录
Environment="PATH=/var/www/crud-app/backend/.venv/bin"   # 让 systemd 找到 venv 里的命令
ExecStart=/var/www/crud-app/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always                        # 进程挂了自动重启
RestartSec=3                          # 重启间隔 3 秒

[Install]
WantedBy=multi-user.target            # 多用户模式（正常开机）下自启
```

```bash
# chown -R：递归改属主/属组
# www-data 是 Nginx 默认用户，后端也用此用户，避免权限问题
sudo chown -R www-data:www-data /var/www/crud-app

# 新建/修改 .service 后必须 reload，systemd 才会重新读配置
sudo systemctl daemon-reload

# enable：开机自启；--now：同时立即 start
sudo systemctl enable --now crud-backend

# 查看服务状态；期望 Active: active (running)
sudo systemctl status crud-backend
```

| 命令 | 作用 |
| --- | --- |
| `chown -R user:group 路径` | 递归修改文件所有者 |
| `systemctl daemon-reload` | 重新加载 systemd 单元配置 |
| `systemctl enable --now 服务` | 开机自启 + 立即启动 |
| `systemctl status 服务` | 查看运行状态与最近日志 |

---

### 2.7 配置 Nginx

```bash
# sites-available：存放所有站点配置（仓库）
sudo nano /etc/nginx/sites-available/crud-app
```

```nginx
server {
    listen 80;                              # 监听 HTTP 80 端口
    server_name _;                          # 匹配任意域名；有域名时填实际域名

    root /var/www/crud-app/frontend/dist;   # 前端静态文件根目录
    index index.html;

    location / {
        # SPA 路由回退：找不到文件时返回 index.html，避免刷新子页面 404
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;   # 把 /api 请求转发给后端
        proxy_set_header Host $host;        # 传递原始 Host 头
        proxy_set_header X-Real-IP $remote_addr;           # 客户端真实 IP
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;        # http 或 https
    }
}
```

```bash
# ln -s：创建软链接（快捷方式）
# sites-enabled 里的链接 = 已启用的站点
sudo ln -s /etc/nginx/sites-available/crud-app /etc/nginx/sites-enabled/

# 删除默认站点，避免与 crud-app 冲突
sudo rm -f /etc/nginx/sites-enabled/default

# 检查 Nginx 配置语法；必须显示 syntax is ok / test is successful
sudo nginx -t

# reload：平滑加载新配置，不断开已有连接（比 restart 更温和）
sudo systemctl reload nginx
```

| 命令 | 作用 |
| --- | --- |
| `ln -s 源 目标` | 创建软链接，启用 Nginx 站点 |
| `nginx -t` | 检查 Nginx 配置语法 |
| `systemctl reload nginx` | 热加载 Nginx 配置 |

---

### 2.8 验证

浏览器访问 **http://<你的公网IP>**，测试增删改查。

---

## 3. 日常更新

```bash
# —— 改后端 ——
# 覆盖服务器上的 app/ 目录
scp -r C:/path/to/crud-app/backend/app root@<你的公网IP>:/var/www/crud-app/backend/

# 仅 requirements.txt 有变化时才需要重装依赖：
# cd /var/www/crud-app/backend && source .venv/bin/activate && pip install -r requirements.txt

# restart：先 stop 再 start，让新代码生效（会短暂断连）
sudo systemctl restart crud-backend

# —— 改前端 ——
cd C:/path/to/crud-app/frontend && npm run build
scp -r dist root@<你的公网IP>:/var/www/crud-app/frontend/

# 前端是静态文件，覆盖即生效，一般无需重启
# 只有改了 Nginx 配置才需要 reload
sudo systemctl reload nginx
```

| 场景 | 命令 |
| --- | --- |
| 改了 Python 代码 | `systemctl restart crud-backend` |
| 改了 requirements.txt | 重装依赖 + `restart crud-backend` |
| 改了前端代码 | `npm run build` + scp dist |
| 改了 Nginx 配置 | `nginx -t` + `reload nginx` |

口诀：**改后端 → restart 后端；改前端 → 传 dist**。

---

## 4. 常见问题排查

| 现象 | 可能原因 | 排查命令 |
| --- | --- | --- |
| 外网打不开，本机 curl 通 | 安全组未放行 80 | 阿里云控制台检查入方向规则 |
| 页面能开，操作失败 | 后端未运行或 Nginx 未代理 `/api` | `systemctl status crud-backend` |
| 502 Bad Gateway | 后端进程挂了或端口不对 | `journalctl -u crud-backend -f` |
| 数据库连接失败 | `.env` 密码/库名错误 | 核对 `.env`；`mysql -u root -p` 手动连 |
| `Could not import module "main"` | uvicorn 启动路径写错 | 用 `app.main:app`，不是 `main:app` |
| 刷新子路由 404 | Nginx 缺 SPA 回退 | 确认 `try_files $uri $uri/ /index.html;` |
| 关终端后端就停 | 还在前台手动跑 | 改用 systemd 常驻 |

```bash
sudo systemctl status crud-backend      # 看服务是否 active (running)，末尾有报错摘要
sudo journalctl -u crud-backend -f      # -f：实时跟踪日志，排 502 首选
sudo tail -f /var/log/nginx/error.log   # Nginx 错误日志（404、502、权限等）
```

---

## 5. 服务器常用命令

### 5.1 资源监控

```bash
free -h                          # 查看内存；重点看 available（还能给新程序用多少）
free -h -s 5                     # 每 5 秒刷新；-s 秒数，Ctrl+C 退出
df -h /                          # 看根分区磁盘使用率；Use% 超 85% 要清理
du -sh /var/www/crud-app/*       # 看项目各子目录占用；-s 汇总，-h 人类可读
du -sh /var/log/*                # 查日志是否膨胀
uptime                           # 系统运行时间 + 负载（1/5/15 分钟三数）
top                              # 交互式实时监控；q 退出
htop                             # 更直观（需 apt install htop）
nproc                            # CPU 逻辑核数；负载长期 > 核数说明 CPU 偏忙
lscpu                            # CPU 型号、架构、核数详情
```

**`free -h` 关键列**：

| 列 | 含义 |
| --- | --- |
| `used` | 已被进程占用 |
| `buff/cache` | 磁盘缓存（可回收，不算真正用光） |
| `available` | **最重要**：估算还能给新程序用的内存 |
| `Swap used` | 交换分区使用量；长期 > 0 说明内存偏紧 |

**`top` 快捷键**：

| 键 | 作用 |
| --- | --- |
| `1` | 展开每个 CPU 核心使用率 |
| `M` | 按内存占用排序 |
| `P` | 按 CPU 占用排序 |
| `q` | 退出 |

---

### 5.2 进程

```bash
ps aux | grep uvicorn              # 查找后端进程；aux = 所有用户所有进程
ps aux | grep mysql                # 查找 MySQL 进程
ps aux --sort=-%mem | head -10     # 内存占用 Top 10；--sort=- 降序
ps aux --sort=-%cpu | head -10     # CPU 占用 Top 10
kill PID                           # 温和结束进程（发 SIGTERM）
kill -9 PID                        # 强制杀死（SIGKILL）；后端优先用 systemctl restart
```

| 列 | 含义 |
| --- | --- |
| `USER` | 运行用户 |
| `PID` | 进程 ID |
| `%CPU` / `%MEM` | CPU / 内存占用百分比 |
| `COMMAND` | 启动命令 |

> 本项目后端应通过 `systemctl restart crud-backend` 重启，不要随手 `kill -9` uvicorn。

---

### 5.3 网络 & 端口

```bash
ss -tlnp                           # 查看 TCP 监听端口
                                   # t=TCP, l=LISTEN, n=数字端口, p=显示进程名
ss -tlnp | grep -E '80|8000|3306'  # 确认 Nginx(80)、后端(8000)、MySQL(3306) 在监听
curl -I http://127.0.0.1:8000/api/health   # -I：只看响应头，不下载 body
ping -c 4 8.8.8.8                  # 测外网连通；-c 4 发 4 个包后停止
```

| 现象 | 可能原因 |
| --- | --- |
| 8000 无监听 | 后端未启动或启动失败 |
| 80 无监听 | Nginx 未启动 |
| 本机 curl 通、外网不通 | 安全组或防火墙拦截 |

---

### 5.4 systemd

| 命令 | 作用 | 典型场景 |
| --- | --- | --- |
| `systemctl start 服务` | 启动服务 | 第一次部署、stop 之后重新拉起 |
| `systemctl stop 服务` | 停止服务 | 维护、临时下线 |
| `systemctl restart 服务` | 先停再启（会断连） | **改后端代码**后让新代码生效 |
| `systemctl reload nginx` | 热加载配置（进程不退出） | **改 Nginx 配置**后平滑生效 |
| `systemctl enable 服务` | 设置开机自启（不一定立刻运行） | 部署时 |
| `systemctl enable --now 服务` | 开机自启 + 立即启动 | 部署一步到位 |
| `systemctl disable 服务` | 取消开机自启（不会停止当前进程） | 下线服务 |
| `systemctl status 服务` | 详细状态 + 最近几行日志 | 排错第一步 |
| `systemctl is-active 服务` | 输出 active/inactive/failed | 脚本体检 |
| `systemctl is-enabled 服务` | 输出 enabled/disabled | 确认是否自启 |
| `systemctl daemon-reload` | 重新读取 `.service` 文件 | **改了 unit 文件后必做** |

**`restart` vs `reload`**：

| 情况 | 用哪个 |
| --- | --- |
| 改了 Python 代码 / `.env` / `requirements.txt` | `restart crud-backend` |
| 改了 `crud-backend.service` | `daemon-reload` → `restart crud-backend` |
| 改了 Nginx 站点配置 | `nginx -t` → `reload nginx` |
| 服务卡死、reload 无效 | `restart` |

```bash
# —— 后端 ——
sudo systemctl restart crud-backend
sudo systemctl daemon-reload && sudo systemctl restart crud-backend   # 改了 .service 后

# —— Nginx ——
sudo nginx -t && sudo systemctl reload nginx

# —— 排错 ——
sudo journalctl -u crud-backend -n 80 --no-pager   # 最近 80 行；--no-pager 直接输出
sudo journalctl -u crud-backend -f                 # 实时跟日志
systemctl cat crud-backend                           # 查看当前生效的 unit 配置
systemctl is-active crud-backend nginx mysql         # 一次查三个服务是否在跑
```

**维护停服顺序**：`stop crud-backend` → 动 MySQL → 改完 `start mysql` → `start crud-backend`（避免后端连着一半的数据库操作）。

---

### 5.5 日志

```bash
sudo journalctl -u crud-backend -n 50        # 最近 50 行后端日志（systemd 管理的服务）
sudo journalctl -u crud-backend -f           # 实时跟踪；-f = follow
sudo journalctl -u crud-backend --since today          # 只看今天的
sudo journalctl -u crud-backend --since "1 hour ago"   # 最近 1 小时
sudo tail -n 100 /var/log/nginx/error.log    # Nginx 错误日志最后 100 行
sudo tail -f /var/log/nginx/error.log        # 实时盯 Nginx 错误
sudo tail -n 100 /var/log/nginx/access.log   # Nginx 访问日志（谁访问、响应码）
```

| 场景 | 优先看 |
| --- | --- |
| 后端 502 / 起不来 | `journalctl -u crud-backend -f` |
| 页面 404 / 静态资源错 | Nginx `error.log` |
| 接口慢、访问量大 | Nginx `access.log` |

---

### 5.6 文件操作

```bash
ls -lah                          # -l 详情，-a 含隐藏文件，-h 人类可读大小
cd /var/www/crud-app             # 切换目录
pwd                              # 打印当前路径
cat 文件                         # 查看小文件全文
less 文件                        # 分页查看大文件；空格翻页，q 退出
head -n 20 文件                  # 看前 20 行
tail -n 20 文件                  # 看后 20 行
nano 文件                        # 编辑；Ctrl+O 保存，Ctrl+X 退出
cp -r 源 目标                    # 复制；-r 递归目录
mv 源 目标                       # 移动或重命名
rm 文件                          # 删除文件（不可恢复，谨慎）
rm -rf 目录                      # 递归强制删除目录（极其谨慎）
chmod 644 文件                   # 改权限：owner 读写，其他人只读
chown -R www-data:www-data 路径  # 递归改属主，部署时让后端进程有读写权限
```

---

### 5.7 系统信息

```bash
uname -a                         # 内核版本、架构
hostname                         # 主机名
whoami                           # 当前登录用户
id                               # 用户 UID/GID、所属组
date                             # 系统时间
timedatectl                      # 时区、NTP 时间同步状态
cat /etc/os-release              # Ubuntu 版本号
lsblk                            # 树状查看磁盘、分区、挂载点
lsblk -f                         # 附带文件系统类型、UUID
```

---

### 5.8 登录后一键体检

```bash
echo "========== 系统 ==========" && uptime
echo "========== 内存 ==========" && free -h
echo "========== 磁盘 ==========" && df -h /
echo "========== 项目占用 ==========" && du -sh /var/www/crud-app/* 2>/dev/null
echo "========== 服务 ==========" && systemctl is-active crud-backend nginx mysql
echo "========== 端口 ==========" && ss -tlnp | grep -E ':80|:8000|:3306'
echo "========== 健康检查 ==========" && curl -s http://127.0.0.1:8000/api/health && echo
# 2>/dev/null：忽略 du 无权限目录的报错
# curl -s：静默模式，不显示进度条
```

**期望结果**：

| 检查项 | 期望 |
| --- | --- |
| 服务 | `crud-backend` / `nginx` / `mysql` 均为 `active` |
| 端口 | `:80`、`:8000`、`:3306` 有 LISTEN |
| 健康检查 | 返回 `{"status":"ok"}` |

---

## 6. 项目信息速查

| 项 | 值 |
| --- | --- |
| 公网 IP | `<你的公网IP>` |
| 项目根目录 | `/var/www/crud-app/` |
| 后端 | `/var/www/crud-app/backend/` → `127.0.0.1:8000` |
| 前端 | `/var/www/crud-app/frontend/dist/` |
| 数据库 | MySQL `crud_demo`，表 `products` |
| systemd 服务 | `crud-backend` → `/etc/systemd/system/crud-backend.service` |
| Nginx 配置 | `/etc/nginx/sites-available/crud-app` |
| 健康检查 | `curl http://127.0.0.1:8000/api/health` → `{"status":"ok"}` |

**快速自检**：

```bash
sudo systemctl status crud-backend       # 后端 running？
curl http://127.0.0.1:8000/api/health  # 返回 ok？
sudo nginx -t                          # Nginx 配置语法正确？
sudo systemctl status nginx            # Nginx running？
# 浏览器 http://<你的公网IP> 能增删改查？
```

---

> **对比**：当前 CI/CD 部署使用 `/opt/crud-app/` + `docker-compose.prod.yml`，镜像来自 GHCR，无需手动装 Python/Nginx/systemd。裸机方案有助于理解各组件职责，Docker 方案把运维简化为 `docker compose pull && up -d`。
