#!/usr/bin/env bash
set -euo pipefail

# Helper to pull image from Aliyun ACR and run via docker-compose.aliyun.acr.yml
# Usage:
#   export ACR_IMAGE=registry.cn-<region>.aliyuncs.com/<ns>/self_diaris:latest
#   ./deploy/scripts/pull-run-from-acr.sh [login]
# If 'login' argument is provided, will attempt docker login using ACR_USERNAME and ACR_PASSWORD env vars.

if [[ "${1:-}" == "login" ]]; then
  if [[ -z "${ACR_IMAGE:-}" ]]; then
    echo "ACR_IMAGE not set" >&2; exit 1
  fi
  if [[ -z "${ACR_USERNAME:-}" || -z "${ACR_PASSWORD:-}" ]]; then
    echo "ACR_USERNAME/ACR_PASSWORD not set" >&2; exit 1
  fi
  REGISTRY="${ACR_IMAGE%%/*}"
  echo "Logging into $REGISTRY ..."
  echo "$ACR_PASSWORD" | docker login "$REGISTRY" -u "$ACR_USERNAME" --password-stdin
fi

if [[ -z "${ACR_IMAGE:-}" ]]; then
  echo "ACR_IMAGE not set, e.g. registry.cn-beijing.aliyuncs.com/<ns>/self_diaris:latest" >&2
  exit 1
fi

echo "Using image: $ACR_IMAGE"

docker compose -f docker-compose.aliyun.acr.yml pull
# If first-time run, ensure .env is prepared per .env.example
if [[ ! -f .env ]]; then
  echo ".env not found. Copying from .env.example ..."
  cp .env.example .env
  echo "Please edit .env and rerun this script if needed."
fi

docker compose -f docker-compose.aliyun.acr.yml up -d

echo "Done. Tail logs with: docker compose -f docker-compose.aliyun.acr.yml logs -f web"