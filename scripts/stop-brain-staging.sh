#!/bin/sh
# Dừng Brain STAGING. Không đụng Brain production (launchd trên Mac Studio).
set -eu
cd "$(dirname "$0")/.."
STG="$PWD/brain-staging"
if [ -f "$STG/brain.pid" ]; then
  PID="$(cat "$STG/brain.pid")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "→ Đã dừng Brain staging pid $PID."
  fi
  rm -f "$STG/brain.pid"
else
  echo "Không có pid Brain staging."
fi
