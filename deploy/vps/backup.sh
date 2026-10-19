#!/bin/sh
# Backup COWORK production trên VPS: gọi CLI trong container, copy ra host, retention 14.
set -eu
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cd "$(dirname "$0")/../.."
BK_DIR="${COWORK_BACKUP_DIR:-/srv/vip-staging/cowork-backups}"
mkdir -p "$BK_DIR"
chmod 700 "$BK_DIR"
docker exec cowork-staging python -m cowork.cli backup >/tmp/cowork-backup-run.log 2>&1
LATEST=$(docker exec cowork-staging sh -c 'ls -t /data/backups/cowork-*.db | head -1')
NAME=$(basename "$LATEST")
docker cp "cowork-staging:$LATEST" "$BK_DIR/$NAME"
chmod 600 "$BK_DIR/$NAME"
python3 - "$BK_DIR/$NAME" <<'PY'
import sqlite3, sys
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
assert c.execute("pragma integrity_check").fetchone()[0] == "ok"
print("BACKUP_OK", sys.argv[1], "users", c.execute("select count(*) from users").fetchone()[0],
      "audit", c.execute("select count(*) from audit_log").fetchone()[0])
PY
ls -1t "$BK_DIR"/cowork-*.db 2>/dev/null | tail -n +15 | xargs -r rm -f
