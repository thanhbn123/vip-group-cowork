#!/bin/sh
# Chạy Brain STAGING ở nền (cổng 8892), dùng bản sao DB + bridge COWORK.
set -eu
cd "$(dirname "$0")/.."
STG="$PWD/brain-staging"
[ -d "$STG/backend" ] || { echo "Chưa provisioning: chạy ./scripts/provision_brain_staging.sh"; exit 78; }
mkdir -p "$STG/logs"
cd "$STG/backend"
set -a
. "$STG/.env"
set +a
if [ -f "$STG/brain.pid" ] && kill -0 "$(cat "$STG/brain.pid")" 2>/dev/null; then
  echo "Brain staging đang chạy (pid $(cat "$STG/brain.pid"))."
  exit 0
fi
nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8892 \
  > "$STG/logs/brain-staging.log" 2>&1 &
echo $! > "$STG/brain.pid"
echo "→ Brain staging pid $(cat "$STG/brain.pid") · log $STG/logs/brain-staging.log"
i=0
while [ $i -lt 40 ]; do
  if curl -s -m 1 http://127.0.0.1:8892/api/health >/dev/null 2>&1; then
    echo "→ Health OK: $(curl -s -m 2 http://127.0.0.1:8892/api/health)"
    exit 0
  fi
  sleep 0.5
  i=$((i+1))
done
echo "CẢNH BÁO: Brain staging chưa trả health sau 20 giây — xem log." >&2
exit 1
