# ROLLBACK — VIP GROUP COWORK

**Nguyên tắc:** không xoá dữ liệu thật; mọi thay đổi production phải có bản sao lưu và điểm quay lui.
**Chưa có thay đổi production nào được áp dụng trong giai đoạn hiện tại.**

---

## 0. BẢN ĐỒ THAY ĐỔI & ĐIỂM QUAY LUI

| Thay đổi | Điểm quay lui | Thời gian | Người quyết định |
|---|---|---|---|
| COWORK lên Mac Studio | dừng LaunchAgent + giữ thư mục/DB | ~10 giây | Controller |
| Tunnel 18835 | `launchctl bootout` | ~5 giây | Controller |
| Caddy block cowork | file `.bak-before-cowork-*` + reload | ~10 giây | Controller |
| Brain bridge | `COWORK_BRIDGE_BAT=0` + restart | ~5 giây | Chủ dự án |
| Brain code | `main.py.bak-before-cowork-*` | ~10 giây | Chủ dự án |
| Dữ liệu COWORK | bản `cowork-YYYYmmdd-HHMMSS.db` | theo bản | Chủ dự án |

DNS **không đổi** nên không cần rollback DNS.

---

## 1. ROLLBACK CADDY (TÊN MIỀN COWORK)

```bash
# Xem bản sao lưu
ls -lt /srv/vip-staging-proxy/Caddyfile.bak-before-cowork-* | head

# Khôi phục bản gần nhất
cp /srv/vip-staging-proxy/Caddyfile.bak-before-cowork-<THOI_DIEM> \
   /srv/vip-staging-proxy/Caddyfile

docker exec vip-staging-caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec vip-staging-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile

# Kiểm tra
curl -sI https://cowork.vipgroup.com.vn/ | head
```

Sau rollback, `cowork.vipgroup.com.vn` có thể trả 308/000 (không còn site block) — đúng trạng thái trước triển khai. Brain `ai.vipgroup.com.vn` không bị ảnh hưởng.

---

## 2. ROLLBACK TUNNEL COWORK

```bash
launchctl bootout gui/$(id -u)/com.vipgroup.cowork.tunnel-vps 2>/dev/null || true
# hoặc kill SSH tunnel đang chạy
pkill -f '18835:127.0.0.1:8899' 2>/dev/null || true
```

Kiểm tra từ VPS: `curl -s http://127.0.0.1:18835/api/health` phải thất bại.
Brain tunnel 18834 **không đụng**.

---

## 3. ROLLBACK COWORK SERVICE

```bash
launchctl bootout gui/$(id -u)/com.vipgroup.cowork 2>/dev/null || true
# Kiểm tra
curl -s http://127.0.0.1:8899/api/health || echo "COWORK đã dừng"
```

Dữ liệu vẫn nằm tại `/Users/macstudio/VIP-AI/cowork/data/cowork.db`; **không xoá**.

### 3.1. Rollback mã nguồn COWORK
Trước mỗi lần nâng cấp, tạo bản lưu:
```bash
cd ~/VIP-AI/cowork
tar czf ~/VIP-AI/cowork/backups/cowork-code-$(date +%Y%m%d-%H%M).tgz \
  --exclude '.venv' --exclude 'data' --exclude 'secrets' --exclude 'brain-staging' .
```
Rollback:
```bash
cd ~/VIP-AI
mv cowork cowork.loi-$(date +%Y%m%d-%H%M)
mkdir cowork
tar xzf cowork.loi-*/backups/cowork-code-<THOI_DIEM>.tgz -C cowork
# giữ nguyên data/ + secrets/ cũ; chạy lại service
```
Sau rollback chạy lại `.venv/bin/python -m pytest -q` (nếu có) và `/api/health`.

### 3.2. Rollback dữ liệu COWORK
Chỉ khi DB hỏng hoặc migration sai:
```bash
cd ~/VIP-AI/cowork
launchctl bootout gui/$(id -u)/com.vipgroup.cowork
cp data/cowork.db data/cowork.db.truoc-rollback-$(date +%Y%m%d-%H%M)
cp data/backups/cowork-<THOI_DIEM>.db data/cowork.db
chmod 600 data/cowork.db
.venv/bin/python -c "import sqlite3;c=sqlite3.connect('data/cowork.db');print(c.execute('PRAGMA integrity_check').fetchone())"
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vipgroup.cowork.plist
```
Lưu ý: audit sau thời điểm backup sẽ mất trong DB khôi phục; **không sửa** bản DB hỏng, giữ lại để điều tra.

---

## 4. ROLLBACK BRAIN BRIDGE

### 4.1. Cách nhanh nhất — tắt cờ (khuyến nghị)
```bash
cd ~/VIP-AI/brain
cp .env .env.truoc-tat-bridge-$(date +%Y%m%d-%H%M)
sed -i '' 's/^COWORK_BRIDGE_BAT=1/COWORK_BRIDGE_BAT=0/' .env
launchctl kickstart -k gui/$(id -u)/com.vipai.brain.backend
curl -s http://127.0.0.1:8891/api/health
# /cowork/vao và /api/cowork/* trả 404
```
Đăng nhập trực tiếp Brain + MFA vẫn hoạt động bình thường.

### 4.2. Gỡ hoàn toàn
```bash
cd ~/VIP-AI/brain
cp backend/app/main.py.bak-before-cowork-<THOI_DIEM> backend/app/main.py
rm -f backend/app/api/cowork_bridge.py
# xoá các dòng COWORK_* khỏi .env nếu không dùng nữa
launchctl kickstart -k gui/$(id -u)/com.vipai.brain.backend
```

### 4.3. Thu hồi phiên Brain do bridge tạo (nếu cần)
```bash
cd ~/VIP-AI/brain
sqlite3 data/vip-brain.db ".backup 'data/vip-brain.truoc-thu-hoi-$(date +%Y%m%d-%H%M).db'"
sqlite3 data/vip-brain.db \
  "UPDATE sessions SET trangThai='thu-hoi' WHERE trangThai='song' AND userId IN (<danh-sach-id>);"
```
Không xoá user shadow nếu chưa rõ; chỉ khoá/thu hồi phiên.

### 4.4. Dữ liệu Brain
Không có thay đổi schema. Bridge chỉ thêm dòng `users` shadow (nếu bật) và `sessions`, `audit`.
Rollback dữ liệu Brain chỉ dùng bản backup `vip-brain.bak-before-cowork-*` và phải có phê duyệt riêng.

---

## 5. KIỂM TRA SAU MỌI ROLLBACK

- [ ] `https://ai.vipgroup.com.vn/api/health` 200.
- [ ] Đăng nhập trực tiếp Brain + MFA 200 (nếu MFA đang bật).
- [ ] COWORK `/api/health` 200 (nếu còn chạy).
- [ ] Nhân viên không thấy module quản trị.
- [ ] Phiên cũ bị thu hồi trả 401/303.
- [ ] Caddy validate/reload không lỗi; chứng chỉ Brain còn hạn.
- [ ] Ghi thời điểm, người thực hiện, lý do, bằng chứng vào `evidence/`.

---

## 6. KHI NÀO KÍCH HOẠT ROLLBACK

| Sự cố | Hành động |
|---|---|
| COWORK 5xx diện rộng | tắt Caddy block trước, giữ service để điều tra |
| Brain bị ảnh hưởng sau bridge | tắt `COWORK_BRIDGE_BAT` ngay, restart Brain |
| Lộ bí mật chia sẻ | tắt bridge, xoay `COWORK_SHARED_SECRET` hai phía, restart |
| Nghi ngờ leo thang quyền | khoá tài khoản liên quan, thu hồi phiên, tắt COWORK, điều tra audit |
| DB COWORK hỏng | dừng service, restore bản backup gần nhất |
| Chứng chỉ không cấp được | gỡ block Caddy, kiểm tra DNS/port 80; không ảnh hưởng Brain |

**Người có quyền quyết định rollback production:** chủ dự án `anh-thanh`; controller thực hiện khi được lệnh.


---

## 7. ĐIỂM QUAY LUI PRODUCTION THỰC TẾ (19/10/2026)

| Lớp | Điểm quay lui |
|---|---|
| COWORK | `launchctl bootout gui/$(id -u)/com.vipgroup.cowork`; code/DB giữ nguyên |
| COWORK DB | `~/VIP-AI/cowork/data/backups/cowork-20261019-180321.db` |
| Tunnel | `launchctl bootout gui/$(id -u)/com.vipgroup.cowork.tunnel-vps`; key `id_ed25519_cowork_vps_tunnel` |
| Caddy | `/home/deploy/Caddyfile.bak-before-cowork-20261019-180126.txt` hoặc `/data/Caddyfile.bak-before-cowork-20261019-180126` |
| Brain code | `~/VIP-AI/brain/backups/cowork-20261019-180225/main.py.bak` + `env.bak` |
| Brain DB | `~/VIP-AI/brain/backups/cowork-20261019-180225/vip-brain-before-cowork.db` |
| Brain bridge tắt nhanh | `COWORK_BRIDGE_BAT=0` trong `~/VIP-AI/brain/.env` + restart backend |
| VPS authorized_keys | `~deploy/.ssh/authorized_keys.bak-before-cowork-20261019-180044` |

**Không đổi DNS**, nên rollback không cần thao tác DNS.
