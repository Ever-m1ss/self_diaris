#!/usr/bin/env bash
set -euo pipefail

# 运行数据库迁移（Render / Railway 都会注入 DATABASE_URL 或使用本地 sqlite3）
python manage.py migrate --noinput

# 收集静态文件（Whitenoise 使用压缩清单，需在构建/启动阶段执行一次）
python manage.py collectstatic --noinput

# 绑定平台提供的 PORT（Railway/Render 均会注入），若为空则默认 8000
PORT="${PORT:-8000}"
echo "Starting gunicorn on port $PORT" >&2
exec gunicorn ll_project.wsgi --workers=2 --bind=0.0.0.0:$PORT --timeout 120
