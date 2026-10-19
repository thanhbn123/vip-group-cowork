#!/bin/sh
# Chạy COWORK ở chế độ local. Không tự deploy, không đụng Brain production.
set -eu
cd "$(dirname "$0")"
umask 077
[ -x .venv/bin/python ] || { echo "Chưa có .venv — chạy ./scripts/bootstrap.sh trước."; exit 78; }
[ -f .env ] || cp .env.example .env
set -a
. ./.env
set +a
exec .venv/bin/python -m uvicorn cowork.main:app \
  --host "${COWORK_HOST:-127.0.0.1}" --port "${COWORK_PORT:-8899}" --no-access-log
