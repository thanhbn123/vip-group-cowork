# KẾ HOẠCH TRIỂN KHAI PRODUCTION — VIP GROUP COWORK

**Trạng thái:** ✅ **ĐÃ ÁP DỤNG 19/10/2026** — chủ dự án duyệt cả 3 cổng.
**Tên miền chính thức:** `https://cowork.vipgroup.com.vn` · Brain: `https://ai.vipgroup.com.vn`

---

## 1. KIẾN TRÚC ĐÍCH

```
Trình duyệt
   │ HTTPS
   ▼
VPS 160.22.170.20 (Caddy v2.11.4, container vip-staging-caddy)
   ├── cowork.vipgroup.com.vn ──► 127.0.0.1:18835 ──┐
   ├── ai.vipgroup.com.vn     ──► 127.0.0.1:18834 ──┤  (Brain, giữ nguyên)
   └── các tên khác (không đổi)                     │
                                                    │ SSH reverse tunnel
                                                    ▼
Mac Studio
   ├── COWORK 127.0.0.1:8899  (LaunchAgent mới, DB riêng cowork.db)
   └── VIP AI BRAIN 127.0.0.1:8891 (LaunchAgent hiện hữu, KHÔNG đổi)
        └── Ollama 127.0.0.1:11434 · qwen2.5:7b-instruct
```

- COWORK và Brain cùng máy Mac Studio nhưng **hai tiến trình, hai DB, hai cổng**.
- COWORK gọi Brain nội bộ `http://127.0.0.1:8891`; trình duyệt mở Brain qua `https://ai.vipgroup.com.vn`.
- Tunnel COWORK dùng cổng **18835**, tách khỏi 18834 của Brain.
- DNS **không đổi** (cowork đã trỏ VPS).

---

## 2. ĐIỀU KIỆN TIÊN QUYẾT

- [ ] Bộ test COWORK xanh: `.venv/bin/python -m pytest -q`.
- [ ] Nghiệm thu local 8 bước đạt (xem `docs/NGHIEM-THU.md`).
- [ ] Kiểm thử SSO COWORK → Brain staging đạt; chat AI Local thật.
- [ ] Có bản sao lưu Caddyfile, code Brain, DB Brain trước khi đổi.
- [ ] Chủ dự án phê duyệt cổng 1 (COWORK), cổng 2 (Caddy), cổng 3 (Brain bridge).

---

## 3. CỔNG 1 — ĐƯA COWORK LÊN MAC STUDIO

### 3.1. Chuẩn bị thư mục
```bash
ssh vip-ai-studio
mkdir -p ~/VIP-AI/cowork/{data,secrets,logs}
chmod 700 ~/VIP-AI/cowork/{data,secrets}
```

### 3.2. Đồng bộ mã (không kèm DB/bí mật/venv)
Từ MacBook:
```bash
rsync -a --exclude '.venv' --exclude '.uv-cache' --exclude 'data' \
  --exclude 'secrets' --exclude 'brain-staging' --exclude 'evidence/screens' \
  --exclude '__pycache__' --exclude '.git' \
  "/Users/viporder/Library/CloudStorage/SynologyDrive-Macbook/VIP GROUP ID/cowork/" \
  macstudio@100.75.51.105:~/VIP-AI/cowork/
```

### 3.3. Môi trường Python
```bash
cd ~/VIP-AI/cowork
/opt/homebrew/bin/uv venv --python 3.12 .venv
UV_CACHE_DIR=$PWD/.uv-cache /opt/homebrew/bin/uv pip install --python .venv/bin/python \
  "fastapi>=0.115" "uvicorn>=0.30" "jinja2>=3.1" "python-multipart>=0.0.20" "httpx>=0.27"
```

### 3.4. `.env` production (mẫu, không chứa bí mật)
```dotenv
COWORK_ENV=production
COWORK_HOST=127.0.0.1
COWORK_PORT=8899
COWORK_PUBLIC_URL=https://cowork.vipgroup.com.vn
COWORK_INTERNAL_URL=http://127.0.0.1:8899
COWORK_COOKIE_SECURE=1
COWORK_TIN_PROXY=1
COWORK_SESSION_HOURS=12
COWORK_IDLE_MINUTES=60
COWORK_PASSWORD_MIN=10
COWORK_TENANT=vip-group
COWORK_BRAIN_ENABLED=1
COWORK_BRAIN_BASE_URL=http://127.0.0.1:8891
COWORK_BRAIN_PUBLIC_URL=https://ai.vipgroup.com.vn
COWORK_BRAIN_TIMEOUT=5
COWORK_BRAIN_TICKET_TTL=60
```
`chmod 600 .env`.

### 3.5. Khởi tạo DB + Super Admin
```bash
cd ~/VIP-AI/cowork
.venv/bin/python -m cowork.cli init
# Sinh mật khẩu một lần, ghi file 0600; KHÔNG in ra terminal
COWORK_OWNER_PASSWORD="$(.venv/bin/python -c 'from cowork.security import gen_mat_khau; print(gen_mat_khau())')"
printf '%s\n' "$COWORK_OWNER_PASSWORD" > secrets/owner-anh-thanh.txt
chmod 600 secrets/owner-anh-thanh.txt
COWORK_OWNER_PASSWORD="$COWORK_OWNER_PASSWORD" .venv/bin/python -m cowork.cli create-owner \
  --id anh-thanh --name "anh-thanh"
unset COWORK_OWNER_PASSWORD
```

### 3.6. LaunchAgent `com.vipgroup.cowork`
Tạo `~/Library/LaunchAgents/com.vipgroup.cowork.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.vipgroup.cowork</string>
  <key>ProgramArguments</key><array>
    <string>/bin/sh</string>
    <string>/Users/macstudio/VIP-AI/cowork/run.sh</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/macstudio/VIP-AI/cowork</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>/Users/macstudio/Library/Logs/VIPAI/cowork.log</string>
  <key>StandardErrorPath</key><string>/Users/macstudio/Library/Logs/VIPAI/cowork.err.log</string>
</dict></plist>
```
```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vipgroup.cowork.plist
launchctl kickstart -k gui/$(id -u)/com.vipgroup.cowork
curl -s http://127.0.0.1:8899/api/health
```

### 3.7. Backup hằng ngày
Thêm LaunchAgent `com.vipgroup.cowork.backup` chạy 03:20:
```bash
/bin/sh -lc 'cd /Users/macstudio/VIP-AI/cowork && .venv/bin/python -m cowork.cli backup'
```
Giữ 14 bản; đẩy bản mã hoá sang Synology theo quy trình Brain hiện có (không dùng chung khoá Brain).

---

## 4. CỔNG 2 — TUNNEL + CADDY

### 4.1. Tunnel COWORK (Mac Studio → VPS)
Tạo `~/VIP-AI/cowork/bin/tunnel-vps.sh`:
```sh
#!/bin/sh
exec ssh -N \
  -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
  -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/Users/macstudio/.ssh/vipai_vps_known_hosts \
  -i /Users/macstudio/.ssh/id_ed25519_cowork_vps_tunnel \
  -R 127.0.0.1:18835:127.0.0.1:8899 deploy@160.22.170.20
```
`chmod 700`; LaunchAgent `com.vipgroup.cowork.tunnel-vps`. Khóa này đã được thêm vào `~deploy/.ssh/authorized_keys` với `permitlisten="127.0.0.1:18835"` (backup `authorized_keys.bak-before-cowork-20261019-180044`).

Kiểm tra từ VPS:
```bash
curl -s http://127.0.0.1:18835/api/health
```

### 4.2. Caddyfile
Sao lưu:
```bash
cp /srv/vip-staging-proxy/Caddyfile \
   /srv/vip-staging-proxy/Caddyfile.bak-before-cowork-$(date +%Y%m%d-%H%M)
```
Dán khối (chi tiết `docs/CAU-HINH-TEN-MIEN.md` §3):
```caddy
cowork.vipgroup.com.vn {
    encode zstd gzip
    header {
        X-Robots-Tag "noindex, nofollow"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }
    reverse_proxy 127.0.0.1:18835 {
        header_up X-Real-IP {remote_host}
        header_down Set-Cookie "^(.*)$" "$1; Secure"
    }
    log {
        output file /data/access-cowork.log { roll_size 10mb roll_keep 5 }
    }
}
```
Validate + reload:
```bash
docker exec vip-staging-caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec vip-staging-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```
Kiểm tra:
```bash
curl -I https://cowork.vipgroup.com.vn/
echo | openssl s_client -connect cowork.vipgroup.com.vn:443 -servername cowork.vipgroup.com.vn \
  2>/dev/null | openssl x509 -noout -subject -dates
```
Caddy tự xin Let's Encrypt (HTTP-01); DNS đã đúng, cổng 80 mở.

---

## 5. CỔNG 3 — BRIDGE BRAIN PRODUCTION (SAU CÙNG)

**Chỉ làm sau khi cổng 1–2 ổn định và có phê duyệt riêng.**

### 5.1. Sao lưu
```bash
cd ~/VIP-AI/brain
cp -a backend/app/main.py backend/app/main.py.bak-before-cowork-$(date +%Y%m%d-%H%M)
cp -a .env .env.bak-before-cowork-$(date +%Y%m%d-%H%M)
sqlite3 data/vip-brain.db ".backup 'data/vip-brain.bak-before-cowork-$(date +%Y%m%d-%H%M).db'"
```

### 5.2. Thêm bridge
```bash
cp ~/VIP-AI/cowork/brain-bridge/cowork_bridge.py ~/VIP-AI/brain/backend/app/api/
```
Thêm vào `backend/app/main.py` (giữ thụt lề **4 dấu cách** trong `tao_app`):
```python
from .api import cowork_bridge  # COWORK BRIDGE
...
    app.include_router(api_router, prefix="/api")
    app.include_router(cowork_bridge.router)  # COWORK BRIDGE
```
Thêm vào `.env` Brain (bí mật lấy từ `~/VIP-AI/cowork/data/brain_secret.key`):
```dotenv
COWORK_BRIDGE_BAT=1
COWORK_SHARED_SECRET=<cùng giá trị với COWORK>
COWORK_INTERNAL_URL=http://127.0.0.1:8899
COWORK_BRIDGE_ALLOW_MFA_USERS=1  # từ 18:35 19/10/2026, sau khi owner bật MFA COWORK
COWORK_BRIDGE_COOKIE_SECURE=1
```
`chmod 600 .env`.

### 5.3. Restart Brain (downtime ngắn)
```bash
launchctl kickstart -k gui/$(id -u)/com.vipai.brain.backend
curl -s http://127.0.0.1:8891/api/health
```
Kiểm tra hồi quy:
- Đăng nhập trực tiếp Brain + MFA vẫn 200.
- `/cowork/vao` không có ticket → 400/401.
- COWORK mở Brain bằng nhân viên → phiên Brain native, AI Local trả lời.
- `anh-thanh` mở qua COWORK → **200** sau khi bật MFA COWORK và `ALLOW_MFA_USERS=1`; test 18:35.

### 5.4. Chưa bỏ MFA
Không đặt `COWORK_BRIDGE_ALLOW_MFA_USERS=1` và không tắt `MFA_BAT` cho tới khi chủ dự án nghiệm thu COWORK an toàn và ra quyết định riêng.

---

## 5.5. GIẢM RỦI RO ACCESS LOG TICKET

- `GET /cowork/vao?ticket=...` xuất hiện trong access log uvicorn/Caddy. Ticket dùng một lần, TTL 60 giây, nhưng vẫn nên:
  - chạy Brain production với access log tắt hoặc lọc path `/cowork/vao`, hoặc
  - chuyển ticket sang POST/form ngắn hạn (thay đổi bridge, cần nghiệm thu lại).
- Không đưa ticket vào báo cáo/ảnh/chat.

## 6. KIỂM THỬ SAU TRIỂN KHAI (PUBLIC)

```bash
# Header & TLS
curl -sI https://cowork.vipgroup.com.vn/ | grep -Ei 'strict-transport|content-security|x-frame|x-content|referrer'
# Đăng nhập sai 6 lần → khoá tạm
# Nhân viên không vào được /tai-khoan, /ban, /vai-tro, /nhat-ky, /cai-dat
# Thu hồi quyền Brain → mở lại bị chặn, phiên Brain cũ 401
# Cross-tenant: b-admin không thấy anh-thanh
# Session revocation: thu hồi phiên → request sau 303 login
```

---

## 7. THỨ TỰ TRIỂN KHAI ĐỀ XUẤT

1. COWORK local/staging nghiệm thu kỹ thuật (đang làm).
2. Chủ dự án duyệt cổng 1 → COWORK lên Mac Studio, chỉ nội bộ `127.0.0.1:8899`.
3. Duyệt cổng 2 → tunnel 18835 + Caddy + TLS; kiểm thử public.
4. Duyệt cổng 3 → bridge Brain; kiểm thử SSO + AI Local.
5. Chủ dự án nghiệm thu 8 bước trên tên miền chính thức.
6. Sau nghiệm thu mới xem xét bỏ MFA/allow MFA users.

**Không có bước nào ở trên được tự động chạy bởi agent.**


---

## 8. KẾT QUẢ ÁP DỤNG THỰC TẾ (19/10/2026)

- COWORK: `/Users/macstudio/VIP-AI/cowork`, LaunchAgent `com.vipgroup.cowork`, pid 18460, health 200.
- Tunnel: `com.vipgroup.cowork.tunnel-vps`, pid 18533, khóa riêng `id_ed25519_cowork_vps_tunnel`, VPS `127.0.0.1:18835` 200.
- Caddy: block đã thêm, validate/reload OK; cert `CN=cowork.vipgroup.com.vn` hạn 17/01/2027; hash `be7a8ef8…5434`.
- Brain bridge: thêm file + 2 dòng main.py; `.env` bật cờ; backup `~/VIP-AI/brain/backups/cowork-20261019-180225/`; health 200, bridge bật.
- Smoke test production: owner login 303; tạo nhân viên 200; nhân viên 303; SSO Brain 303/200; chat local/real qwen2.5:7b-instruct, task `T-G02-000035`, chi phí 0; MFA owner 403 (trước 18:35); sau đó owner mở Brain 200, thu hồi COWORK 403/Brain 401; archive 303.
- Backup COWORK: `com.vipgroup.cowork.backup` 03:20; bản `cowork-20261019-180321.db`.
- Bằng chứng: `evidence/PRODUCTION-DEPLOY-20261019.md`, `evidence/PRODUCTION-smoke-20261019.json`.


---

## 9. CUTOVER SANG VPS (19/10/2026 20:26)

- COWORK: VPS `127.0.0.1:8899` (container `cowork-staging`), Caddy `cowork` → 8899.
- Brain: `COWORK_INTERNAL_URL=https://cowork.vipgroup.com.vn`.
- Nghiệm thu 8/8; owner smoke PASS.
- Backup VPS local 03:20; offsite Synology 03:50; Studio backup/offsite tắt.
- Chi tiết: `evidence/PRODUCTION-CUTOVER-20261019.md`.
