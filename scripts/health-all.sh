#!/bin/sh
# Kiểm tra sức khoẻ các thành phần COWORK local/staging.
# Không đụng production; chỉ gọi HTTP + SQLite read-only.
set -u
cd "$(dirname "$0")/.."
FAIL=0

check() {
  NAME="$1"; URL="$2"; EXPECT="${3:-200}"
  CODE=$(curl -s -m 3 -o /tmp/cowork-health.$$ -w "%{http_code}" "$URL" 2>/dev/null || echo 000)
  if [ "$CODE" = "$EXPECT" ]; then
    echo "OK   $NAME ($CODE) $URL"
  else
    echo "FAIL $NAME ($CODE, cần $EXPECT) $URL"
    FAIL=1
  fi
  rm -f /tmp/cowork-health.$$
}

check "COWORK"        "http://127.0.0.1:8899/api/health" 200
check "BRAIN staging" "http://127.0.0.1:8892/api/health" 200
check "BRAIN bridge"  "http://127.0.0.1:8892/api/cowork/suc-khoe" 200
check "OLLAMA tunnel" "http://127.0.0.1:11434/api/tags" 200

if [ -f data/cowork.db ]; then
  DB=$(sqlite3 data/cowork.db "PRAGMA integrity_check;" 2>/dev/null || echo "loi")
  if [ "$DB" = "ok" ]; then echo "OK   COWORK DB integrity"; else echo "FAIL COWORK DB: $DB"; FAIL=1; fi
else
  echo "FAIL chưa có data/cowork.db"; FAIL=1
fi

echo "---"
[ "$FAIL" = 0 ] && echo "TẤT CẢ THÀNH PHẦN SẴN SÀNG" || echo "CÓ THÀNH PHẦN CHƯA SẴN SÀNG"
exit "$FAIL"
