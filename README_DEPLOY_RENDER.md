# 在 Render 免费层部署本项目（支持自定义域名）

适用目标：想要免费托管 Django 项目，并绑定自己的域名（会有空闲休眠/冷启动，个人项目可接受）。

## 1. 预备与代码

- 已包含生产所需文件：
  - `requirements.txt`（含 gunicorn/whitenoise/psycopg2-binary）
  - `Procfile`（使用 gunicorn 启动）
  - `ll_project/settings.py` 已做生产化：
    - SECRET_KEY/DEBUG 来自环境变量
    - 支持 `DATABASE_URL`（Postgres）
    - Whitenoise 提供静态文件服务，`STATIC_ROOT=staticfiles`
    - 根据 `RENDER_EXTERNAL_HOSTNAME` 自动设置 `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`

## 2. 在 Render 上创建服务

1) 将仓库推到 GitHub。

2) 在 Render 控制台创建：
- New > Web Service > 选择仓库
- Build Command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`（也可只写第一段，collectstatic 可在部署后 shell 执行）
- Start Command: Render 会读取根目录 `Procfile`，无需手填（若需：`gunicorn ll_project.wsgi --workers=2 --bind=0.0.0.0:$PORT --timeout 120`）

3) 环境变量（Environment):
- `SECRET_KEY`：设置为随机长字符串
- `DEBUG`：`False`
- `RENDER_EXTERNAL_HOSTNAME`：Render 部署完成后会自动注入（无需你手动）
- （数据库）在 Render 创建一个免费的 PostgreSQL，然后将其 `External Database URL` 复制为：
  - `DATABASE_URL`（若前缀为 `postgres://` 本项目会自动兼容为 `postgresql://`）

（可选但强烈推荐）Cloudinary 媒体存储：
- 注册 Cloudinary 免费账号，获取 `cloud_name`、`api_key`、`api_secret`
- 在 Render → Environment 添加：
  - `CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>`
  - 设置后，项目会自动启用 Cloudinary 作为默认文件存储，避免 Render 重建时附件丢失。

4) 首次部署完成后，打开 Render Shell 执行：

```
python manage.py migrate
python manage.py collectstatic --noinput
```

然后访问 Render 提供的子域名确认运行。

## 3. 绑定自定义域名（可选）

- 在 Render 的服务页面 > Settings > Custom Domains 添加你的域名。
- 按提示在域名 DNS 提供商处添加 CNAME 记录指向 Render 子域。
- Render 会自动颁发 HTTPS 证书。

注意：
- 自定义域名添加后，无需额外改代码；`ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS` 建议一并加入该域名，可通过 Render 环境变量覆写：
  - `ALLOWED_HOSTS`（例如 `your.com,www.your.com,你的-render-host`）
  - `CSRF_TRUSTED_ORIGINS`（例如 `https://your.com,https://www.your.com,https://你的-render-host`）
（如需，我可将 settings 改为从以上环境变量读取并合并）

## 4. 媒体文件（用户上传）

Render 免费层的磁盘会随部署重建，适合代码与静态文件，不适合持久媒体。建议：
- 使用 Cloudinary（免费层）或 Backblaze B2/S3 作为对象存储，配合 `django-storages`。
- 简单做法（暂时）：继续使用本地 `MEDIA_ROOT`，但要注意重新部署会丢失历史上传。

如需接入 Cloudinary：
- `pip install django-storages[boto3]` 或 `cloudinary`
- 在 settings 中配置对应 Storage Backend（可帮你改好）。

## 5. 本地运行

```
# Windows PowerShell
python -m venv ll_env
ll_env\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## 6. 常见问题

- 403 CSRF：确保 `CSRF_TRUSTED_ORIGINS` 包含你的域名（含 https 前缀），Render 环境变量会自动注入内置主机。
- 静态文件 404：确认 `collectstatic` 已执行且 `STATIC_ROOT` 正确，并已启用 Whitenoise。
- 数据库连接失败：检查 `DATABASE_URL` 是否使用 `postgresql://`，项目内已自动兼容旧的 `postgres://`。

如需，我可以继续把对象存储对接/ALLOWED_HOSTS 读取自定义环境变量化，或帮你在 Render 控制台完成首次部署。