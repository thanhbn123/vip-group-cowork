# BIÊN BẢN TRIỂN KHAI PRODUCTION — VIP GROUP COWORK

**Ngày:** 19/10/2026 · **Phê duyệt:** chủ dự án chọn **“Duyệt cả 3 cổng — go-live đầy đủ”**
**Tên miền:** COWORK `https://cowork.vipgroup.com.vn` · Brain `https://ai.vipgroup.com.vn`
**Kết quả:** ✅ GO-LIVE 3 cổng — COWORK public, TLS hợp lệ, Brain bridge hoạt động, AI Local trả lời thật.

---

## 1. TRẠNG THÁI SAU TRIỂN KHAI

| Thành phần | Trạng thái | Bằng chứng |
|---|---|---|
| COWORK public | ✅ 200 `/api/health`, trang đăng nhập 200 | `PRODUCTION-deploy-20261019.txt` |
| TLS | ✅ Let's Encrypt `CN=cowork.vipgroup.com.vn`, hạn 17/01/2027 | `openssl s_client` |
| Security headers | ✅ CSP, HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy | header public |
| COWORK LaunchAgent | ✅ `com.vipgroup.cowork`, pid 18460 | `launchctl` |
| Tunnel 18835 | ✅ `com.vipgroup.cowork.tunnel-vps`, pid 18533 | VPS `127.0.0.1:18835` 200 |
| Caddy block | ✅ đã thêm, validate + reload, hash `be7a8ef8…5434` | Caddy log + file |
| Brain production | ✅ health 200, bridge bật, pid 18620 | `127.0.0.1:8891` |
| AI Local | ✅ `qwen2.5:7b-instruct`, `providerId=local`, `nhan=real`, chi phí 0 | smoke test |
| Backup COWORK | ✅ job `com.vipgroup.cowork.backup` 03:20; bản `cowork-20261019-180321.db` | log backup |
| Audit IP | ✅ IP public thật `14.190.214.49`; call nội bộ `127.0.0.1` | audit tail |

---

## 2. COWORK TRÊN MAC STUDIO

- Thư mục: `/Users/macstudio/VIP-AI/cowork`
- DB: `data/cowork.db` (2 user: owner + 1 QA đã lưu trữ; 11 audit tại thời điểm chụp)
- `.env`: production, `COWORK_TIN_PROXY=1`, `COWORK_COOKIE_SECURE=1`, Brain base `http://127.0.0.1:8891`, public URL chính thức.
- Venv: `.venv` Python 3.12.15, FastAPI 0.147.0.
- LaunchAgent: `~/Library/LaunchAgents/com.vipgroup.cowork.plist`, log `~/Library/Logs/VIPAI/cowork.log`.
- Mật khẩu owner production: `~/VIP-AI/cowork/secrets/owner-anh-thanh.txt` (0600, không in ra tài liệu).

### 2.1. Tunnel
- Script: `~/VIP-AI/cowork/bin/tunnel-vps.sh`
- Khóa riêng: `~/.ssh/id_ed25519_cowork_vps_tunnel` (mới tạo, chỉ dùng tunnel)
- VPS `authorized_keys` đã thêm dòng `restrict,port-forwarding,command="/bin/false",permitlisten="127.0.0.1:18835"` (backup `authorized_keys.bak-before-cowork-20261019-180044`).
- Tunnel: `-R 127.0.0.1:18835:127.0.0.1:8899`.
- LaunchAgent: `com.vipgroup.cowork.tunnel-vps`, log `cowork-tunnel.log/.err.log`.

---

## 3. CADDY / TLS

- Caddyfile sống: `/srv/vip-staging-proxy/Caddyfile` (root), mount vào container `vip-staging-caddy`.
- Trước: hash `c2674057…dad3c`.
- Sau: hash `be7a8ef8…5434`.
- Backup:
  - `/home/deploy/Caddyfile.bak-before-cowork-20261019-180126.txt`
  - `/data/Caddyfile.bak-before-cowork-20261019-180126`
- `caddy validate` → **Valid configuration**; `caddy reload` exit 0.
- Chứng chỉ tự cấp thành công qua HTTP-01; log `certificate obtained successfully`.
- Cảnh báo không chặn: Caddyfile chưa `caddy fmt` (dòng 53).

**Không đổi DNS** (đã trỏ VPS từ trước).

---

## 4. BRAIN PRODUCTION — BRIDGE

- Backup trước khi vá: `~/VIP-AI/brain/backups/cowork-20261019-180225/`
  - `main.py.bak`
  - `env.bak`
  - `vip-brain-before-cowork.db` (SQLite backup API)
- Đã thêm: `backend/app/api/cowork_bridge.py`; `main.py` +2 dòng import/include (giữ thụt lề); compile OK.
- `.env` thêm:
  - `COWORK_BRIDGE_BAT=1`
  - `COWORK_SHARED_SECRET=<khớp COWORK data/brain_secret.key>`
  - `COWORK_INTERNAL_URL=http://127.0.0.1:8899`
  - `COWORK_BRIDGE_ALLOW_MFA_USERS=1` (từ 18:35; trước đó 0)
  - `COWORK_BRIDGE_COOKIE_SECURE=1`
- Restart `com.vipai.brain.backend` → health 200; bridge `{"bridge":"bat","cookieSecure":true,"choMfa":false,"coBiMat":true}`.
- `/cowork/vao` không ticket → 400; `/api/cowork/thu-hoi` không chữ ký → 401.
- MFA Brain **vẫn bật**; owner trực tiếp vẫn dùng MFA như cũ.
- **Không xoá/sửa dữ liệu Brain production**; bridge chỉ thêm shadow/session/audit khi có ticket.

---

## 5. SMOKE TEST PRODUCTION (THẬT, KHÔNG MOCK)

Chạy trên Mac Studio qua tên miền chính thức, owner password đọc tại chỗ:

| Bước | Kết quả |
|---|---|
| Owner đăng nhập COWORK public | 303 |
| Tạo nhân viên `prod-qa-180302` Ban Kinh doanh | 200 |
| Nhân viên đăng nhập | 303 |
| Module nhân viên | dashboard, brain, tasks, knowledge, usage |
| Mở Brain từ COWORK | 303 → `/cowork/vao?ticket=...` 303 → `/api/auth/toi` 200 đúng user |
| Chat AI Local | 200 · `providerId=local` · `nhan=real` · `qwen2.5:7b-instruct` · chi phí 0 · task `T-G02-000035` · 901 ký tự |
| MFA guard owner | 403 “Chưa bỏ MFA cho tài khoản này” (trước 18:35; sau đó owner mở được — §11) |
| Thu hồi quyền Brain | COWORK `/brain` 403; Brain `/api/auth/toi` 401 |
| Cấp lại | COWORK `/brain` 200 |
| Lưu trữ tài khoản QA | 303, `archived` |

Bằng chứng: `evidence/PRODUCTION-smoke-20261019.json`, `evidence/PRODUCTION-deploy-20261019.txt`.

---

## 6. BACKUP & ROLLBACK

### 6.1. Backup
- COWORK: `com.vipgroup.cowork.backup` 03:20 hằng ngày; `data/backups/cowork-*.db`, plaintext local (0600). Bản test: `cowork-20261019-180321.db`.
- Brain: backup cũ `com.vipai.brain.backup-vipbrain` vẫn chạy; bản trước bridge `backups/cowork-20261019-180225/vip-brain-before-cowork.db`.

### 6.2. Rollback nhanh
```sh
# COWORK
launchctl bootout gui/$(id -u)/com.vipgroup.cowork
# Caddy
cp /home/deploy/Caddyfile.bak-before-cowork-20261019-180126.txt /srv/vip-staging-proxy/Caddyfile  # cần quyền root/docker
docker exec vip-staging-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
# Brain bridge (tắt cờ)
cd ~/VIP-AI/brain && sed -i '' 's/^COWORK_BRIDGE_BAT=1/COWORK_BRIDGE_BAT=0/' .env
launchctl kickstart -k gui/$(id -u)/com.vipai.brain.backend
# Gỡ hoàn toàn: restore main.py.bak + xoá cowork_bridge.py; restart
```
- Quy trình đầy đủ: `docs/ROLLBACK.md`.

---

## 7. HẠN CHẾ / VIỆC TIẾP THEO

1. **COWORK chưa có MFA**: hiện chỉ mật khẩu + rate limit; nên bổ sung TOTP cho Super Admin trước khi mở rộng người dùng.
2. **Owner đã mở Brain qua COWORK** từ 18:35 (`ALLOW_MFA_USERS=1`) sau khi bật MFA COWORK; rollback `=0` nếu cần.
3. **Offsite backup COWORK** chưa tự động sang Synology (Brain đã có); cần bổ sung job mã hoá nếu muốn.
4. **Caddyfile chưa `caddy fmt`** — chỉ là cảnh báo định dạng.
5. **HEAD `/` trả 405** (FastAPI chỉ có GET); health check dùng `/api/health`.
6. **Nhân viên QA `prod-qa-180302`** đã lưu trữ, audit còn; không xoá cứng.
7. **Caddy backup `/data`** đã có; host backup ở `/home/deploy/`.

---

## 8. BỔ SUNG MFA TOTP (19/10/2026 18:11)

- Backup trước khi deploy:
  - Code: `~/VIP-AI/backups/cowork-code-before-mfa-20261019-181120.tar.gz`
  - DB: `data/backups/cowork-20261019-181120.db` (schema 1, 2 user, 11 audit)
  - `.env`: `~/VIP-AI/backups/cowork-env-before-mfa-20261019-181120`
- Migration tự động khi restart: schema **1 → 2**, thêm `users.mfa_enabled`, `users.mfa_secret`, bảng `mfa_challenges`, `mfa_backup_codes`; dữ liệu cũ giữ nguyên.
- Health sau restart: 200; users vẫn 2; 2 user MFA columns; 2 bảng MFA.
- Smoke production với admin tạm `prod-mfa-181256` (bản cuối; bản trước `prod-mfa-181144`):
  - Tạo admin 200 · login trước MFA 303 · bật MFA 200 · logout 303
  - Login mật khẩu → **303 `/dang-nhap/mfa`**
  - Nhập TOTP → **303 `/`**, `/api/me` 200
  - Owner archive admin 303
- Bằng chứng: `evidence/PRODUCTION-mfa-smoke-20261019.json`.
- Admin test `prod-mfa-181138` (lần chạy lỗi PYTHONPATH) và `prod-mfa-181256` (bản cuối; bản trước `prod-mfa-181144`) đã lưu trữ; audit còn.
- **Owner production đã bật MFA** lúc 18:25 (xem §10); file secret/mã dự phòng 0600 trên Studio.
- Break-glass: `ssh vip-ai-studio 'cd ~/VIP-AI/cowork && .venv/bin/python -m cowork.cli mfa-reset --id <id>'`.
- Test local: `tests/test_mfa_controller.py` 9 test; full suite **95 passed**.

---

## 9. BACKUP OFFSITE COWORK (SCRIPT ĐÃ KIỂM THỬ)

- Script: `scripts/backup-cowork-offsite.sh` — gọi backup SQLite trên Studio, scp, kiểm `integrity_check`, mã hoá AES-256-CBC/PBKDF2 200k bằng `~/VIP-AI/keys/backup.key`, retention 14 bản.
- Chạy thử với đích tạm: **PASS** — `users=5`, `schema=2`, file `.enc` 224K; xoá bản tạm sau test.
- Bằng chứng: `evidence/FINAL-cowork-offsite-test.txt`.
- LaunchAgent mẫu: `deploy/com.vipgroup.cowork.offsite.plist` (03:40).
- **Đã cài job tự động** 18:21: `~/Library/LaunchAgents/com.vipgroup.cowork.offsite.plist`, script `~/VIP-AI/bin/backup-cowork-offsite.sh`, lịch 03:40.
- Chạy thử: `status-cowork.json` ok, `users=5`, `schema=2`, file `cowork-20261019-182146.db.enc` 224K tại `SAO LUU VPS/VIP-AI-COWORK`.
- Backup local 03:20 trên Studio vẫn đang chạy.


---

## 10. OWNER MFA + HEAD + CADDY FMT (19/10/2026 18:25)

- Owner `anh-thanh` đã bật MFA TOTP:
  - Secret + 10 mã dự phòng: `~/VIP-AI/cowork/secrets/owner-mfa-anh-thanh.txt` (0600).
  - Kiểm tra: đăng nhập mật khẩu → `/dang-nhap/mfa` 303; nhập TOTP → `/` 303; `/api/me` 200; logout 303.
  - `active_mfa=1`; bằng chứng `evidence/PRODUCTION-owner-mfa-20261019.json`.
- `HEAD /` đã trả **200** (trước 405); health check dùng được HEAD/GET `/api/health`.
- Caddyfile đã `caddy fmt`:
  - Backup: `~/Caddyfile.bak-before-fmt-20261019-182534.txt` + `/data/Caddyfile.bak-before-fmt-...`.
  - Hash trước `be7a8ef8…` → sau `eea7ed56…`; validate/reload OK; cert/health giữ nguyên.
- Full suite **95 passed**.


---

## 11. OWNER MỞ BRAIN QUA COWORK (19/10/2026 18:35)

- Owner đã bật MFA COWORK → đặt `COWORK_BRIDGE_ALLOW_MFA_USERS=1` trong Brain `.env` (backup `~/VIP-AI/backups/brain-env-before-allow-mfa-20261019-183435`).
- Bridge báo `choMfa:true`; health 200.
- Test production thật:
  - COWORK mật khẩu → MFA 303; mở Brain → `/cowork/vao` 303 → `/api/auth/toi` 200 đúng `anh-thanh`.
  - Chat: `providerId=local`, `nhan=real`, `qwen2.5:7b-instruct`, chi phí 0, task `T-G02-000036`, 737 ký tự.
  - Logout COWORK → Brain `/api/auth/toi` **401** (thu hồi).
- Bằng chứng: `evidence/PRODUCTION-owner-brain-20261019.json`.
- Rollback: đặt `COWORK_BRIDGE_ALLOW_MFA_USERS=0` + restart Brain.
