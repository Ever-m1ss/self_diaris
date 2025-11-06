#!/usr/bin/env bash
set -euo pipefail

# Run migrations before starting the app. We assume DATABASE_URL is set by Render.
python manage.py migrate --noinput

# Optionally you can uncomment the next line if you expect dynamic static updates
# python manage.py collectstatic --noinput

exec gunicorn ll_project.wsgi --workers=2 --bind=0.0.0.0:$PORT --timeout 120
