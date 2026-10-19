#!/bin/sh
# Backup COWORK production trên VPS → Synology, mã hoá AES-256.
set -eu
KEY="$HOME/VIP-AI/keys/backup.key"
DEST="${COWORK_OFFSITE_DEST:-$HOME/Library/CloudStorage/SynologyDrive-Macbook/SAO LUU VPS/VIP-AI-COWORK-VPS}"
STATUS="${COWORK_OFFSITE_STATUS:-$HOME/VIP-AI/backups/status-cowork-vps.json}"
SSH="/usr/bin/ssh -T -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -i $HOME/.ssh/viporder_staging viporder-staging"
fail() { printf '{"luc":"%s","ok":false,"loi":"%s"}\n' "$(date -Iseconds)" "$1" > "$STATUS"; echo "COWORK_VPS_OFFSITE_FAIL $1" >&2; exit 1; }
[ -f "$KEY" ] || fail "không thấy key"
mkdir -p "$DEST"
OUT=$($SSH 'docker exec cowork-staging python -m cowork.cli backup') || fail "backup remote lỗi"
REMOTE=$(printf '%s\n' "$OUT" | sed -n 's/^Backup: \([^ ]*\.db\).*/\1/p' | tail -1)
case "$REMOTE" in /data/backups/cowork-*.db) ;; *) fail "đường dẫn backup lạ: $REMOTE" ;; esac
TMP=$(mktemp -d /tmp/cowork-vps-offsite.XXXXXX); chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT
$SSH "docker exec cowork-staging cat '$REMOTE'" > "$TMP/live.db" || fail "tải DB lỗi"
chmod 600 "$TMP/live.db"
[ "$(/usr/bin/sqlite3 "$TMP/live.db" 'PRAGMA integrity_check;')" = "ok" ] || fail "integrity lỗi"
USERS=$(/usr/bin/sqlite3 "$TMP/live.db" 'select count(*) from users;')
SCHEMA=$(/usr/bin/sqlite3 "$TMP/live.db" "select value from meta where key='schema_version';")
[ "$USERS" -ge 1 ] || fail "không có user"
TS=$(date +%Y%m%d-%H%M%S); ENC="$DEST/cowork-vps-$TS.db.enc"
/usr/bin/openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -in "$TMP/live.db" -out "$ENC" -pass "file:$KEY" || fail "mã hoá lỗi"
chmod 600 "$ENC"
ls -1t "$DEST"/cowork-vps-*.db.enc 2>/dev/null | tail -n +15 | xargs -I{} rm -f "{}"
printf '{"luc":"%s","ok":true,"remote":"%s","enc":"%s","users":%s,"schema":"%s"}\n' \
  "$(date -Iseconds)" "$REMOTE" "$ENC" "$USERS" "$SCHEMA" > "$STATUS"
echo "COWORK_VPS_OFFSITE_OK $ENC users=$USERS schema=$SCHEMA"
