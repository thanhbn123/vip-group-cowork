# PRODUCTION READINESS — COWORK

**Ngày:** 19/10/2026 · **Trạng thái:** LOCAL/STAGING READY · **PRODUCTION: CHƯA TRIỂN KHAI**
**Tên miền:** `https://cowork.vipgroup.com.vn` (DNS đúng, chưa có site block Caddy)

---

## 1. BẢNG SẴN SÀNG

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| Ứng dụng chạy local | ✅ | `127.0.0.1:8899`, `/api/health` ok |
| DB schema + seed | ✅ | `cowork.db`, version 1 |
| Đăng nhập ID + scrypt | ✅ | 14 test + test bổ sung |
| Phiên máy chủ + thu hồi | ✅ | cookie HttpOnly/SameSite, idle/absolute |
| CSRF form | ✅ | thiếu/sai token → 403 |
| Rate limit đăng nhập | ✅ | 5 sai/10 phút theo user+IP |
| 5 vai trò + quyền module | ✅ | chống leo thang, scope ban |
| Tenant isolation | ✅ | tenant B không thấy tenant A |
| Audit append-only | ✅ | trigger chặn UPDATE/DELETE |
| Màn hình quản trị | ✅ | dashboard, tài khoản, ban, vai trò, quyền, module, nhật ký, cài đặt |
| Brain ticket one-time + HMAC | ✅ | TTL 60s, chống replay |
| Brain staging + AI Local | ✅/đang nghiệm thu | DB bản sao, `qwen2.5:7b-instruct` |
| Caddy block cowork | ⏳ chưa áp dụng | chờ phê duyệt cổng 2 |
| Tunnel 18835 | ⏳ chưa áp dụng | chờ phê duyệt cổng 2 |
| Bridge Brain production | ⏳ chưa áp dụng | chờ phê duyệt cổng 3 |
| Sao lưu COWORK định kỳ | ⏳ local có CLI; production cần LaunchAgent | theo kế hoạch |
| MFA cho COWORK | ❌ chưa có | chỉ mật khẩu; Super Admin nên cân nhắc bổ sung |
| IP thật sau proxy | ✅ đã vá | `COWORK_TIN_PROXY=1` + `web.ip_cua` đọc `X-Real-IP`; `run.sh --no-proxy-headers` |
| Trusted host / HSTS | ✅ sau Caddy | HSTS bật khi `X-Forwarded-Proto=https` |

---

## 2. KHOẢNG TRỐNG PHẢI XỬ LÝ TRƯỚC KHI MỞ PUBLIC

### 2.1. IP thật sau Caddy — ĐÃ VÁ
- `COWORK_TIN_PROXY=1` (production) + `web.ip_cua()` đọc `X-Real-IP` do Caddy ghi đè; `run.sh` chạy `--no-proxy-headers` để không tin `X-Forwarded-For` tự khai.
- Rate limit đăng nhập + `audit_log.ip` dùng IP thật; khi `TIN_PROXY=0` header bị bỏ qua.
- Test: `tests/test_controller_ops.py` (4 ca IP) — header giả bị bỏ, header hợp lệ được nhận.
- Còn lại: cột `sessions.ip` vẫn lấy peer socket (127.0.0.1 sau Caddy); không ảnh hưởng rate limit/audit. Nếu cần hiển thị IP thật trong phiên, truyền `ip_cua` vào `auth.tao_phien` ở bước sau.

### 2.2. Đăng xuất COWORK — ĐÃ THU HỒI BRAIN
- `auth_routes.dang_xuat` gọi `brain.thu_hoi_phien()` khi user có `brain.view`; phiên Brain native bị thu hồi ngay, audit ghi `brainRevoke`.
- Test: `tests/test_controller_ops.py::test_dang_xuat_thu_hoi_phien_brain`.

### 2.3. MFA cho Super Admin COWORK (khuyến nghị)
- COWORK hiện chỉ mật khẩu. Nếu public Internet, nên thêm TOTP cho `super_admin`/`admin` hoặc giới hạn IP quản trị.
- Không bắt buộc cho nghiệm thu hiện tại, nhưng là rủi ro còn lại.

### 2.4. Caddy/Header
- Caddy block đã soạn; cần kiểm tra `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` sau khi public.
- Caddyfile root-owned; luôn sao lưu trước khi sửa.

### 2.5. Brain production
- Bridge mặc định `COWORK_BRIDGE_ALLOW_MFA_USERS=0`; giữ nguyên tới nghiệm thu.
- Brain `/api/settings` authz gap và header chưa persist là nợ cũ của Brain, không do COWORK; ghi nhận để chủ dự án xử lý riêng.
- Không xoá dữ liệu test Brain nếu chưa có phê duyệt.

### 2.6. Vận hành
- LaunchAgent COWORK + backup + tunnel cần cài theo `docs/TRIEN-KHAI-PRODUCTION.md`.
- Giám sát `/api/health` và dung lượng DB.
- Log COWORK/uvicorn không chứa mật khẩu/token; audit không chứa bí mật.

---

## 3. KIỂM THỬ BẮT BUỘC TRƯỚC KHI PUBLIC

- [ ] `pytest` toàn bộ xanh.
- [ ] Đăng nhập đúng/sai, rate limit, CSRF, session revocation.
- [ ] Nhân viên chỉ thấy module được cấp; route admin 403.
- [ ] Quản trị cấp dưới không tạo/sửa Super Admin, không vượt phạm vi.
- [ ] Cross-tenant 404.
- [ ] Brain ticket one-time; chat `providerId=local`, `nhan=real`.
- [ ] Thu hồi quyền Brain → phiên Brain cũ 401.
- [ ] Header bảo mật + TLS + cookie Secure.
- [x] IP thật sau proxy đúng (đã có test).
- [ ] Backup/restore thử trên bản sao.

---

## 4. QUYẾT ĐỊNH CỦA CHỦ DỰ ÁN

1. Duyệt cổng 1 (COWORK lên Mac Studio)?
2. Duyệt cổng 2 (tunnel + Caddy + TLS)?
3. Duyệt cổng 3 (bridge Brain production)?
4. Có yêu cầu MFA cho COWORK trước khi public không?
5. Có giới hạn IP cho `/cai-dat`, `/tai-khoan` không?

### 2.7. Access log chứa ticket (từ AG-05)
- Brain staging/uvicorn và Caddy access log ghi `/cowork/vao?ticket=...`. Ticket one-time/TTL 60s nên rủi ro thấp, nhưng trước khi public nên:
  - tắt/che access log cho path `/cowork/vao`, hoặc
  - chuyển ticket sang POST/fragment.
- Chưa sửa production; ghi nhận để xử lý khi duyệt cổng 3.

**Chưa có câu trả lời nào được mặc định là CÓ.**

---

## 5. DIỄN TẬP ROLLBACK (19/10/2026)

- `./scripts/rollback-drill.sh` — **PASS**:
  - Backup SQLite: 17 user · 275 audit · integrity `ok`.
  - Restore ra DB tạm: counts khớp 6 bảng (users/audit/sessions/role_permissions/modules/tenants).
  - Chạy server trên DB khôi phục cổng 8902: đăng nhập `anh-thanh` PASS, 15 module.
  - Xoá DB tạm; giữ backup.
- Bằng chứng: `evidence/FINAL-rollback-drill.txt`.
- Caddy block đã **validate cú pháp** trên VPS bằng tệp tạm, live hash không đổi: `evidence/FINAL-caddy-validate.txt`.

**Vẫn chưa có thay đổi production nào.**
