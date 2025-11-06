# 部署到阿里云（ECS/容器）

本文档给出两种简单路径：

- Docker Compose（推荐）：最少运维，单机即可跑。
- 传统方式（可选）：Nginx + Gunicorn + systemd（需要手工配置）。

## 一、Docker Compose（推荐）

前提：你的阿里云机器已安装 Docker 与 Docker Compose。

1) 在服务器上克隆仓库并进入目录：

```bash
# 在服务器上
sudo apt update && sudo apt install -y git
# 拉取你的仓库
git clone <your_repo_url>
cd self_diaris
```

2) 复制环境文件并修改：

```bash
cp .env.example .env
# 编辑 .env，填入 SECRET_KEY、CLOUDINARY_URL（可选）、公网域名/IP 到 ALLOWED_HOSTS_EXTRA 等
```

关键变量说明：
- SECRET_KEY：Django 安全密钥，必须随机且保密。
- DEBUG：生产必须为 false。
- POSTGRES_*：Postgres 容器的库名/用户/密码。
- DATABASE_URL：应用连接字符串（默认已指向 compose 内的 `db` 服务）。
- CLOUDINARY_URL：媒体存储（推荐启用）。
- ALLOWED_HOSTS_EXTRA：你的服务器公网 IP 或域名（多值以逗号分隔）。
- CSRF_TRUSTED_ORIGINS_EXTRA：HTTPS 域名，以 `https://` 开头，多值以逗号分隔。

3) 启动：

```bash
# 首次启动（后台运行）
sudo docker compose -f docker-compose.aliyun.yml up -d --build

# 查看日志（可选）
sudo docker compose -f docker-compose.aliyun.yml logs -f web
```

4) 验证：
- 浏览器访问 `http://<服务器公网IP>:8000/healthz` 应返回 `ok`。
- 若要 80/443 端口访问，请在阿里云安全组放行对应端口，并按需在前面加 Nginx / Caddy 做反向代理和 HTTPS。

5) 升级：

```bash
# 拉取最新代码并重建
sudo docker compose -f docker-compose.aliyun.yml pull
sudo docker compose -f docker-compose.aliyun.yml up -d --build
```

6) 备份数据库：

```bash
# 导出
sudo docker exec -t $(sudo docker ps -qf name=_db) pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
# 导入（示例）
sudo docker exec -i $(sudo docker ps -qf name=_db) psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < backup.sql
```

## 二、传统方式（可选）

若不使用 Docker，可在 ECS 上：

- 安装 Python 3.11、PostgreSQL、Nginx。
- 创建虚拟环境并安装 `requirements.txt`。
- 运行 `python manage.py migrate && python manage.py collectstatic`。
- Gunicorn 作为 systemd 服务启动（示例 unit 文件可按需添加）。
- Nginx 反代到 `127.0.0.1:8000`，静态由 Whitenoise 提供或直接交给 Nginx。

如果你需要，我可以继续为传统方式生成 Nginx 配置与 systemd unit 文件模板。
已生成示例配置：

```
deploy/nginx/diary.conf              # HTTP 反代
deploy/nginx/diary-ssl.conf          # HTTPS 模板（需证书）
deploy/systemd/gunicorn.service      # 非 Docker 模式示例 unit
deploy/systemd/self-diaris-compose.service  # Docker Compose 管理 unit
```

### 使用 systemd 管理 Docker Compose

```bash
sudo cp deploy/systemd/self-diaris-compose.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now self-diaris-compose.service
```

更新代码后重启：

```bash
cd /opt/self_diaris
git pull origin main
sudo systemctl restart self-diaris-compose.service
```

### 使用 Nginx 配置

```bash
sudo cp deploy/nginx/diary.conf /etc/nginx/conf.d/diary.conf
sudo nginx -t && sudo systemctl reload nginx
```

HTTPS：替换 `YOUR_DOMAIN` 后：

```bash
sudo cp deploy/nginx/diary-ssl.conf /etc/nginx/conf.d/diary-ssl.conf
sudo nginx -t && sudo systemctl reload nginx
```

证书可用 Certbot 自动获取：

```bash
sudo yum install -y certbot python3-certbot-nginx  # 或 apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com --agree-tos -m you@example.com --redirect --non-interactive
```
