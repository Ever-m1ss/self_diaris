#!/usr/bin/env bash
set -euo pipefail

# 如果设置了 DATABASE_URL 且不是 sqlite，等待数据库就绪（在 docker-compose 中 db 带 healthcheck 也能保证顺序）
if [ -n "${DATABASE_URL:-}" ] && [[ "$DATABASE_URL" != sqlite* ]]; then
	echo "Waiting for database..." >&2
	for i in {1..60}; do
		python - <<'PY'
import os, sys, socket
from urllib.parse import urlparse
url = os.environ.get('DATABASE_URL','')
if url.startswith('postgres://'):
		url = url.replace('postgres://','postgresql://',1)
p = urlparse(url)
host = p.hostname or 'db'
port = p.port or 5432
try:
		with socket.create_connection((host, int(port)), timeout=2):
				print('DB reachable')
				sys.exit(0)
except Exception:
		sys.exit(1)
PY
		if [ $? -eq 0 ]; then
			break
		fi
		sleep 2
		echo "Retrying DB..." >&2
	done
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

PORT="${PORT:-8000}"
echo "Starting gunicorn on port $PORT" >&2
exec gunicorn ll_project.wsgi --workers=2 --bind=0.0.0.0:$PORT --timeout 120
