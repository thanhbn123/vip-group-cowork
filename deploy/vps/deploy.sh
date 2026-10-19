#!/bin/sh
# Cập nhật + build lại COWORK staging trên VPS. Chạy tại /srv/vip-staging/cowork.
set -eu
cd "$(dirname "$0")/../.."
echo "[1/4] git pull"
git pull --ff-only
echo "[2/4] build + up"
docker compose -f deploy/vps/docker-compose.yml up -d --build
echo "[3/4] chờ health"
i=0
while [ $i -lt 40 ]; do
  if curl -fsS -m 2 http://127.0.0.1:8899/api/health >/dev/null 2>&1; then break; fi
  sleep 0.5; i=$((i+1))
done
curl -fsS -m 3 http://127.0.0.1:8899/api/health
echo
echo "[4/4] trạng thái"
docker compose -f deploy/vps/docker-compose.yml ps
