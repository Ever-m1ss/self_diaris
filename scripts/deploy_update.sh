#!/usr/bin/env bash
set -euo pipefail

# Quick deploy/update helper for ECS
# - Pull latest code, run migrations, collectstatic, restart gunicorn service.
# Usage:
#   bash scripts/deploy_update.sh [--no-migrate] [--service diary.service]

SERVICE_NAME="diary.service"
DO_MIGRATE=1

for arg in "$@"; do
  case "$arg" in
    --no-migrate) DO_MIGRATE=0 ; shift ;;
    --service) SERVICE_NAME="$2" ; shift 2 ;;
    *) shift ;;
  esac
done

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "[1/5] Git pull"
git pull --ff-only

echo "[2/5] Activate venv"
VENV="$PROJECT_DIR/../venv"
if [ -d "$PROJECT_DIR/venv" ]; then VENV="$PROJECT_DIR/venv"; fi
source "$VENV/bin/activate"

if [ $DO_MIGRATE -eq 1 ]; then
  echo "[3/5] Django migrate"
  python manage.py migrate --noinput
else
  echo "[3/5] Skip migrate"
fi

echo "[4/5] Collect static"
python manage.py collectstatic --noinput

echo "[5/5] Restart service: $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager -l | sed -n '1,20p'

echo "Done."
