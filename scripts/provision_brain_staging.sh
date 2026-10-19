#!/bin/sh
# Cấp phát Brain STAGING trên MacBook từ bản sao production trong Synology Drive.
# - KHÔNG sửa bản production.
# - DB là BẢN SAO (SQLite backup API), không phải DB live.
# - Cổng 8892, DB riêng, frontend riêng.
set -eu
cd "$(dirname "$0")/.."
umask 077

PROD="${VIP_BRAIN_PROD:-$HOME/Library/CloudStorage/SynologyDrive-Macbook/Thành bộ não/production/vip-ai-brain}"
STG="$PWD/brain-staging"
PORT="${BRAIN_STAGING_PORT:-8892}"

if [ ! -d "$PROD/backend/app" ]; then
  echo "Không thấy bản production tại: $PROD" >&2
  exit 78
fi

echo "→ Tạo thư mục staging: $STG"
rm -rf "$STG"
mkdir -p "$STG/data" "$STG/backend" "$STG/frontend" "$STG/logs"

echo "→ Sao chép mã nguồn (không gồm .git, DB, pycache)…"
rsync -a --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude 'vip-brain.db*' --exclude '.venv' \
  "$PROD/backend/" "$STG/backend/"
rsync -a --exclude '.git' --exclude '__pycache__' \
  "$PROD/frontend/" "$STG/frontend/"

echo "→ Sao lưu DB production bằng SQLite backup API (chỉ đọc)…"
PROD_DB="$PROD/backend/vip-brain.db"
[ -f "$PROD_DB" ] || PROD_DB="$HOME/VIP-AI/brain/data/vip-brain.db"
if [ ! -f "$PROD_DB" ]; then
  echo "Không thấy DB production để sao chép." >&2
  exit 78
fi
sqlite3 "$PROD_DB" ".backup '$STG/data/vip-brain-staging.db'"
chmod 600 "$STG/data/vip-brain-staging.db"
echo "→ DB staging: $STG/data/vip-brain-staging.db"

# Bản sao production có thể chưa cấu hình model Local; E2E cần model thật đang chạy
# trong Ollama. Chỉ sửa DB STAGING, không bao giờ chạm DB production.
echo "→ Cấu hình provider Local cho staging (qwen2.5:7b-instruct)…"
.venv/bin/python - "$STG/data/vip-brain-staging.db" <<'PY'
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
row = conn.execute("SELECT giaTri FROM settings WHERE khoa='providerConfig'").fetchone()
cfgs = json.loads(row[0]) if row else []
for c in cfgs:
    if c.get("providerId") == "local":
        c["modelId"] = "qwen2.5:7b-instruct"
        c["bat"] = True
        c["timeoutS"] = 180
conn.execute("UPDATE settings SET giaTri=? WHERE khoa='providerConfig'",
             (json.dumps(cfgs, ensure_ascii=False),))
conn.commit()
conn.close()
PY

echo "→ Cài dependency cho Brain staging…"
mkdir -p .uv-cache
UV_CACHE_DIR="$PWD/.uv-cache" /opt/homebrew/bin/uv venv --python 3.12 "$STG/backend/.venv" >/dev/null
UV_CACHE_DIR="$PWD/.uv-cache" /opt/homebrew/bin/uv pip install --python "$STG/backend/.venv/bin/python" \
  "fastapi>=0.115" "uvicorn>=0.30" "httpx>=0.27" "pydantic>=2.7" "pypdf>=6.1" \
  "python-multipart>=0.0.20" >/dev/null

echo "→ Sinh bí mật chia sẻ COWORK ↔ BRAIN…"
[ -f data/brain_secret.key ] || .venv/bin/python -c 'from cowork import config; print(config.BRAIN_SHARED_SECRET)' >/dev/null
SECRET="$(cat data/brain_secret.key)"

# LƯU Ý: start-brain-staging.sh `source` tệp này bằng shell, nên MỌI giá trị có dấu cách
# PHẢI được quote. Thiếu quote → shell tách chuỗi và báo "GROUP: command not found".
cat > "$STG/.env" <<EOF
# BRAIN STAGING — bản sao, không phải production.
VIP_BRAIN_DB="$STG/data/vip-brain-staging.db"
VIP_BRAIN_BO_QUA_ENV=0
AUTH_DEV_MODE=0
VIP_AI_LOCAL_ONLY=1
NO_CLOUD=1
# E2E nghiệm thu cần gọi THẬT Ollama local. VIP_AI_LOCAL_ONLY=1 (fail-closed trong
# app/providers) mới là chốt chặn provider đám mây; NO_CLOUD=1 chỉ là dấu cấu hình.
CHO_PHEP_GOI_THAT=1
OLLAMA_URL=http://127.0.0.1:11434
VIP_CODE_AGENT_CHO_PHEP_CHAY_MA=0
MFA_BAT=1
MFA_USER_ID=anh-thanh
MFA_SECRET_FILE="$HOME/VIP-AI/brain/mfa_secret.txt"
TIN_PROXY=0
PYTHONPYCACHEPREFIX="$STG/pycache"
COWORK_BRIDGE_BAT=1
COWORK_SHARED_SECRET=$SECRET
COWORK_INTERNAL_URL=http://127.0.0.1:8899
COWORK_BRIDGE_ALLOW_MFA_USERS=0
COWORK_BRIDGE_COOKIE_SECURE=0
EOF
chmod 600 "$STG/.env"

echo "→ Áp dụng bridge COWORK vào bản staging…"
.venv/bin/python scripts/apply_bridge.py "$STG"

echo "→ Xong. Chạy Brain staging:"
echo "   ./scripts/start-brain-staging.sh"
echo "   (cần tunnel Ollama: ssh -f -N -L 11434:127.0.0.1:11434 vip-ai-studio)"
