#!/bin/sh
# Backup COWORK từ Mac Studio → Synology, mã hoá AES-256 (job riêng, không đụng Brain).
set -eu
KEY="$HOME/VIP-AI/keys/backup.key"
DEST="${COWORK_OFFSITE_DEST:-$HOME/Library/CloudStorage/SynologyDrive-Macbook/SAO LUU VPS/VIP-AI-COWORK}"
STATUS="${COWORK_OFFSITE_STATUS:-$HOME/VIP-AI/backups/status-cowork.json}"
SSH="/usr/bin/ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOME/.ssh/vipai_studio_ts_known_hosts -i $HOME/.ssh/id_ed25519_vip_ai_studio vip-ai-studio"
SCP="/usr/bin/scp -q -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOME/.ssh/vipai_studio_ts_known_hosts -i $HOME/.ssh/id_ed25519_vip_ai_studio"
fail() { printf '{"luc":"%s","ok":false,"loi":"%s"}\n' "$(date -Iseconds)" "$1" > "$STATUS"; echo "COWORK_OFFSITE_FAIL $1" >&2; exit 1; }
[ -f "$KEY" ] || fail "không thấy key"
mkdir -p "$DEST"
# 1. Studio tạo bản backup SQLite nhất quán
OUT=$($SSH 'cd /Users/macstudio/VIP-AI/cowork && .venv/bin/python -m cowork.cli backup') || fail "backup remote lỗi"
REMOTE=$(printf '%s\n' "$OUT" | sed -n 's/^Backup: \([^ ]*\.db\).*/\1/p' | tail -1)
case "$REMOTE" in /Users/macstudio/VIP-AI/cowork/data/backups/cowork-*.db) ;; *) fail "đường dẫn backup lạ" ;; esac
TMP=$(mktemp -d /tmp/cowork-offsite.XXXXXX); chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT
$SCP "macstudio@100.75.51.105:$REMOTE" "$TMP/live.db" || fail "scp lỗi"
chmod 600 "$TMP/live.db"
# 2. integrity + dữ liệu tối thiểu
[ "$(/usr/bin/sqlite3 "$TMP/live.db" 'PRAGMA integrity_check;')" = "ok" ] || fail "integrity lỗi"
USERS=$(/usr/bin/sqlite3 "$TMP/live.db" 'select count(*) from users;')
SCHEMA=$(/usr/bin/sqlite3 "$TMP/live.db" "select value from meta where key='schema_version';")
[ "$USERS" -ge 1 ] || fail "không có user"
TS=$(date +%Y%m%d-%H%M%S); ENC="$DEST/cowork-$TS.db.enc"
/usr/bin/openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -in "$TMP/live.db" -out "$ENC" -pass "file:$KEY" || fail "mã hoá lỗi"
chmod 600 "$ENC"
# 3. retention 14 bản .enc
ls -1t "$DEST"/cowork-*.db.enc 2>/dev/null | tail -n +15 | xargs -I{} rm -f "{}"
printf '{"luc":"%s","ok":true,"remote":"%s","enc":"%s","users":%s,"schema":"%s"}\n' \
  "$(date -Iseconds)" "$REMOTE" "$ENC" "$USERS" "$SCHEMA" > "$STATUS"
echo "COWORK_OFFSITE_OK $ENC users=$USERS schema=$SCHEMA"
