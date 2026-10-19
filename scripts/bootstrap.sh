#!/bin/sh
# Bootstrap COWORK local: venv, .env, schema, Super Admin anh-thanh.
# KHÔNG in mật khẩu ra màn hình; mật khẩu ghi vào secrets/ (0600).
set -eu
cd "$(dirname "$0")/.."
umask 077

if [ ! -x .venv/bin/python ]; then
  echo "→ Tạo môi trường Python 3.12…"
  mkdir -p .uv-cache
  UV_CACHE_DIR="$PWD/.uv-cache" /opt/homebrew/bin/uv venv --python 3.12 .venv
  UV_CACHE_DIR="$PWD/.uv-cache" /opt/homebrew/bin/uv pip install --python .venv/bin/python \
    "fastapi>=0.115" "uvicorn>=0.30" "jinja2>=3.1" "python-multipart>=0.0.20" \
    "httpx>=0.27" "pytest>=8" >/dev/null
fi

[ -f .env ] || cp .env.example .env
set -a
. ./.env
set +a

.venv/bin/python -m cowork.cli init
mkdir -p secrets data
chmod 700 secrets data

OWNER_ID="${COWORK_OWNER_ID:-anh-thanh}"
OWNER_NAME="${COWORK_OWNER_NAME:-anh-thanh}"
RESET=""
[ "${1:-}" = "--reset" ] && RESET="--reset"

if .venv/bin/python -m cowork.cli show-user "$OWNER_ID" >/dev/null 2>&1 && [ -z "$RESET" ]; then
  echo "→ Super Admin '$OWNER_ID' đã tồn tại. Giữ nguyên mật khẩu hiện tại."
  echo "  (Dùng ./scripts/bootstrap.sh --reset nếu chủ dự án yêu cầu đặt lại.)"
  exit 0
fi

PW="$(.venv/bin/python -c 'from cowork.security import gen_mat_khau; print(gen_mat_khau())')"
PW_FILE="secrets/owner-$OWNER_ID.txt"
printf '%s\n' "$PW" > "$PW_FILE"
chmod 600 "$PW_FILE"
COWORK_OWNER_PASSWORD="$PW" .venv/bin/python -m cowork.cli create-owner \
  --id "$OWNER_ID" --name "$OWNER_NAME" $RESET

echo "→ Đã tạo Super Admin: $OWNER_ID"
echo "→ Mật khẩu một lần: $PW_FILE (0600) — chủ dự án đọc và lưu an toàn."
echo "→ Chạy: ./run.sh   ·   URL local: ${COWORK_PUBLIC_URL:-http://127.0.0.1:8899}"
