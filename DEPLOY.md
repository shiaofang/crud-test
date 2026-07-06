# Ubuntu 22.04 部署指南（新手向）

本指南把项目部署到你的阿里云 ECS（Ubuntu 22.04）。最终效果：
浏览器访问 `http://你的公网IP` → Nginx 提供前端页面，前端调用 `/api` → Nginx 反代到后端 FastAPI → 读写 MySQL。

> 从你截图看，服务器上 **MySQL(3306)** 和 **80 端口** 已经在跑了，所以下面 MySQL/Nginx 的安装步骤如果已装好可以跳过，直接用。

整体架构：

```
用户浏览器
   │  http://公网IP
   ▼
Nginx (80)
   ├── /            → 前端静态文件 dist/
   └── /api/        → 反向代理 → uvicorn(127.0.0.1:8000) → MySQL(127.0.0.1:3306)
```

---

## 0. 准备工作

用 SSH 登录服务器（你截图里的用户是 `ubuntu`）：

```bash
ssh ubuntu@你的公网IP
```

更新系统并安装基础工具：

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nginx git
```

> 阿里云安全组要放行 **80 端口**（在阿里云控制台 → 安全组 → 入方向规则里添加，源 `0.0.0.0/0`，端口 `80`）。这一步很多新手会漏，导致本地能通、外网打不开。

---

## 1. 配置 MySQL

登录 MySQL（如果是 root 无密码或用 sudo）：

```bash
sudo mysql
```

创建数据库和一个专用账号（把密码换成你自己的强密码）：

```sql
CREATE DATABASE crud_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'crud_user'@'localhost' IDENTIFIED BY '你的强密码';
GRANT ALL PRIVILEGES ON crud_demo.* TO 'crud_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

---

## 2. 上传代码到服务器

把项目放到 `/var/www/crud-app`。两种方式选一种：

**方式 A：用 Git（推荐）**

```bash
sudo mkdir -p /var/www/crud-app
sudo chown -R $USER:$USER /var/www/crud-app
git clone 你的仓库地址 /var/www/crud-app
```

**方式 B：本地直接传（在你 Windows 电脑上执行）**

```bash
scp -r C:\Users\95230\Desktop\test\* ubuntu@你的公网IP:/tmp/crud-app
# 然后在服务器上：
sudo mkdir -p /var/www/crud-app && sudo mv /tmp/crud-app/* /var/www/crud-app/
sudo chown -R $USER:$USER /var/www/crud-app
```

---

## 3. 部署后端

```bash
cd /var/www/crud-app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

创建 `.env` 配置文件：

```bash
cp .env.example .env
nano .env
```

填入第 1 步创建的数据库信息，`CORS_ORIGINS` 生产环境用同域可以留空或写公网地址：

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=crud_user
DB_PASSWORD=你的强密码
DB_NAME=crud_demo
CORS_ORIGINS=http://你的公网IP
```

先手动跑一下确认能连上数据库（`Ctrl+C` 停止）：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另开一个终端测试：curl http://127.0.0.1:8000/api/health  应返回 {"status":"ok"}
```

### 用 systemd 常驻后端

```bash
sudo cp /var/www/crud-app/deploy/crud-backend.service /etc/systemd/system/
# 确保目录属主是 www-data（Nginx 用户）
sudo chown -R www-data:www-data /var/www/crud-app
sudo systemctl daemon-reload
sudo systemctl enable --now crud-backend
sudo systemctl status crud-backend    # 看到 active (running) 就成功
```

> 后续更新代码后重启后端：`sudo systemctl restart crud-backend`
> 查看日志排错：`sudo journalctl -u crud-backend -f`

---

## 4. 部署前端

前端有两种打包方式，任选：

**方式 A：在服务器上打包**（需要 Node 18+）

```bash
# 安装 Node（若服务器没有）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

cd /var/www/crud-app/frontend
npm install
npm run build     # 产物在 dist/
```

**方式 B：在本地打包后只传 dist**（服务器不用装 Node）

```bash
# 本地 Windows 执行
cd C:\Users\95230\Desktop\test\frontend
npm run build
scp -r dist ubuntu@你的公网IP:/var/www/crud-app/frontend/
```

> 生产环境前端通过 Nginx 和后端同域，请求 `/api/...` 会自动走到后端，无需改前端代码。

---

## 5. 配置 Nginx

```bash
sudo cp /var/www/crud-app/deploy/nginx.conf /etc/nginx/sites-available/crud-app
sudo ln -s /etc/nginx/sites-available/crud-app /etc/nginx/sites-enabled/
# 可选：去掉默认站点，避免冲突
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t          # 测试配置语法
sudo systemctl reload nginx
```

现在打开浏览器访问 `http://你的公网IP`，应该能看到商品管理界面，并可以正常增删改查。

---

## 6. 常见问题排查

| 现象 | 排查方向 |
| --- | --- |
| 外网打不开，本地 curl 正常 | 阿里云安全组没放行 80 端口 |
| 页面能开，但操作报错/加载失败 | 后端没起来：`systemctl status crud-backend`；或 Nginx `/api` 代理没配好 |
| 后端起不来，日志报数据库连接错误 | `.env` 里账号密码/库名不对，或 MySQL 用户权限问题 |
| 502 Bad Gateway | 后端进程挂了或端口不是 8000，查 `journalctl -u crud-backend -f` |
| 前端刷新子路由 404 | Nginx 的 `try_files ... /index.html` 没生效 |

---

## 7.（可选）配置 HTTPS

有域名的话，用 Certbot 一键签发免费证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名
```

---

## 更新流程速查

```bash
cd /var/www/crud-app && git pull          # 拉最新代码
# 后端有依赖变化：
source backend/.venv/bin/activate && pip install -r backend/requirements.txt
sudo systemctl restart crud-backend
# 前端有改动：
cd frontend && npm install && npm run build
sudo systemctl reload nginx
```
