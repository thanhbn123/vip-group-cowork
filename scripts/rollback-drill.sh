#!/bin/sh
# Diễn tập backup/restore COWORK — KHÔNG chạm DB live.
# 1. Sao lưu bằng SQLite backup API.
# 2. Khôi phục bản sao lưu mới nhất ra DB tạm.
# 3. So sánh số dòng + integrity.
# 4. Chạy thử server trên DB tạm (cổng 8902), đăng nhập owner, đọc /api/me.
# 5. Dừng server tạm, xoá DB tạm; giữ bản backup.
set -eu
cd "$(dirname "$0")/.."
umask 077

echo "# ROLLBACK DRILL — $(date '+%Y-%m-%d %H:%M:%S %z')"
.venv/bin/python -m cowork.cli backup | tee /tmp/cowork-drill-backup.txt
BK=$(ls -t data/backups/cowork-*.db 2>/dev/null | head -1)
[ -n "$BK" ] || { echo "FAIL: không có bản backup"; exit 1; }
echo "backup=$BK"
cp "$BK" data/restore-drill.db
chmod 600 data/restore-drill.db

.venv/bin/python - <<'PY'
import sqlite3
live = sqlite3.connect("data/cowork.db")
rest = sqlite3.connect("data/restore-drill.db")
try:
    for db in (live, rest):
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    for table in ("users", "audit_log", "sessions", "role_permissions", "modules", "tenants"):
        a = live.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        b = rest.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: live={a} restore={b} {'OK' if a == b else 'LỆCH'}")
        if a != b:
            raise SystemExit(f"FAIL: lệch số dòng bảng {table}")
    print("integrity=ok · counts=khớp")
finally:
    live.close(); rest.close()
PY

# Chạy thử server trên DB khôi phục
COWORK_PORT=8902 COWORK_DB_PATH="$PWD/data/restore-drill.db" \
  nohup .venv/bin/python -m uvicorn cowork.main:app \
  --host 127.0.0.1 --port 8902 --no-access-log --no-proxy-headers \
  > data/restore-drill.log 2>&1 &
PID=$!
echo "restore_server_pid=$PID"
i=0
while [ $i -lt 30 ]; do
  if curl -s -m 1 http://127.0.0.1:8902/api/health >/dev/null 2>&1; then break; fi
  sleep 0.3
  i=$((i+1))
done
COWORK_OWNER_PASSWORD="$(cat secrets/owner-anh-thanh.txt)" .venv/bin/python - <<'PY'
import httpx, re, pathlib
B="http://127.0.0.1:8902"
pw=pathlib.Path("secrets/owner-anh-thanh.txt").read_text().strip()
c=httpx.Client(follow_redirects=True, timeout=10)
r=c.get(B+"/dang-nhap"); assert r.status_code==200
csrf=re.search(r'name="_csrf" value="([^"]+)"', r.text).group(1)
r=c.post(B+"/dang-nhap", data={"userId":"anh-thanh","matKhau":pw,"_csrf":csrf,"next":"/"})
assert r.status_code==200 and "Bảng điều khiển" in r.text, r.status_code
me=c.get(B+"/api/me").json()["data"]
print("restore_login=PASS user=", me["id"], "role=", me["vaiTro"], "modules=", len(me["modules"]))
PY
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
rm -f data/restore-drill.db data/restore-drill.log
echo "Đã xoá DB tạm; backup giữ tại $BK"
echo "ROLLBACK DRILL: PASS"
