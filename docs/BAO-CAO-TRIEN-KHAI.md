# BÁO CÁO TRIỂN KHAI & BÀN GIAO — VIP GROUP COWORK

**Ngày:** 19/10/2026 · **Controller:** DeepSeek · **Chủ dự án:** anh-thanh
**Tên miền chính thức:** COWORK `https://cowork.vipgroup.com.vn` · Brain `https://ai.vipgroup.com.vn`
**Trạng thái:** LOCAL/STAGING **ĐẠT** · PRODUCTION **ĐÃ GO-LIVE 19/10/2026**

---

## 1. KẾT LUẬN ĐIỀU HÀNH

1. **Chưa từng có COWORK**: không source, UI, backend, DB. Đã khảo sát và xác nhận; không có gì để "sửa lại".
2. **VIP AI Brain production được giữ nguyên**: 7 user, 1 tenant, DB `ok`, vẫn `127.0.0.1:8891` trên Mac Studio. Không sửa DB, không restart production, không đổi Caddy/DNS.
3. **COWORK đã được xây dựng mới**, tách biệt Brain: FastAPI + SQLite riêng, 5 vai trò, module registry, tenant, audit, phiên, phân quyền, 15 màn hình.
4. **Cầu nối COWORK ↔ Brain đã chạy thật trên staging**: ticket one-time + HMAC → phiên Brain native → chat AI Local `qwen2.5:7b-instruct`, `providerId=local`, `nhan=real`, chi phí 0; thu hồi quyền chặn ngay cả COWORK và phiên Brain.
5. **Nghiệm thu kỹ thuật 8/8 bước + 6/6 bảo mật E2E đạt** (AG-05), có bằng chứng HTTP/JSON; controller cũng tự chạy lại độc lập.
6. **Tên miền `cowork.vipgroup.com.vn` đã live HTTPS/TLS** từ 19/10/2026; chủ dự án đã duyệt cả 3 cổng.
7. **MFA Brain vẫn bật**: `anh-thanh` mở Brain qua COWORK bị chặn 403 có chủ ý cho tới khi COWORK được nghiệm thu an toàn. Nhân viên không MFA mở bình thường.

> **Một câu:** COWORK đã sẵn sàng để chủ dự án nghiệm thu tại local/staging; production là 3 cổng có phê duyệt, không tự deploy.

---

## 2. ĐÃ HOÀN THIỆN

| Hạng mục | Kết quả |
|---|---|
| Khảo sát COWORK/Brain | Báo cáo `docs/BAO-CAO-KHAO-SAT.md`; xác nhận COWORK chưa tồn tại |
| Kiểm tra tên miền | `docs/CAU-HINH-TEN-MIEN.md`; DNS đúng, Caddy thiếu block, cổng 18835 trống |
| Lõi ID & phiên | ID + scrypt, phiên máy chủ, CSRF, rate limit, đổi/đặt lại mật khẩu, thu hồi phiên |
| RBAC 5 vai trò | Super Admin, Quản trị cấp dưới, Trưởng ban, Nhân viên, Đối tác |
| Chống leo thang | Không tạo/sửa vai trò ngang/cao hơn; không sửa Super Admin; subset quyền; scope ban |
| Tenant isolation | Mọi truy vấn lọc tenant; tenant B không thấy tenant A |
| Audit append-only | Trigger chặn UPDATE/DELETE; màn lọc + xuất CSV |
| Module registry | 15 module, bật/tắt, quyền xem/sử dụng |
| Màn hình | Dashboard, tài khoản, ban, vai trò, phân quyền, module, nhật ký, cài đặt, Brain, hồ sơ, đối tác |
| MFA TOTP COWORK | Bật/tắt, login challenge 5 phút, 10 mã dự phòng, CLI reset break-glass |
| Brain bridge | Ticket one-time 60s, HMAC hai chiều, phiên Brain native, thu hồi tức thời |
| AI Local | Chat thật qua Ollama trên Mac Studio, không cloud/mock |
| Tài liệu | README, khảo sát, tên miền, triển khai, rollback, nghiệm thu, ma trận yêu cầu |
| Bộ test | **94 test PASS** (lõi + 5 làn agent + controller), full suite xanh |

---

## 3. KIẾN TRÚC ĐÃ DỰNG

```
COWORK (FastAPI + SQLite cowork.db)
  ├── Auth: ID + scrypt, session cookie, CSRF, rate limit
  ├── RBAC: role_permissions + user_permissions allow/deny
  ├── Tenant + department + admin_scopes
  ├── Audit append-only
  ├── Module registry + UI
  └── Brain client: ticket one-time + HMAC
          │
          ▼
VIP AI BRAIN staging (bản sao DB, 127.0.0.1:8892)
  ├── bridge /cowork/vao  (ticket → phiên native)
  ├── /api/cowork/thu-hoi (HMAC)
  ├── audit + session + shadow user
  └── Ollama qwen2.5:7b-instruct (Mac Studio, local-only)
```

- COWORK DB: `cowork.db` (không phải `vip-brain.db`).
- Brain staging DB: bản sao `vip-brain-staging.db`; production không đổi.
- Chính thức: COWORK `cowork.vipgroup.com.vn`; Brain `ai.vipgroup.com.vn`.

---

## 4. KẾT QUẢ 5 LÀN AGENT

| Làn | Kết quả chính | Test / bằng chứng |
|---|---|---|
| **AG-01 Frontend** | Bảng responsive dạng card ≤720px, mobile registry, bỏ link chết, `[hidden]`, focus/sidebar inert, aria, 57 ảnh 1440/390, 0 tràn ngang/0 lỗi console/0 link chết | 6 test, `tests/test_ui_ag01.py`, `evidence/AG01-report.md` |
| **AG-02 Identity** | Sửa 2 lỗi thật: xoá bộ đếm sai sau đăng nhập đúng; không thu hồi phiên vừa tạo khi trùng giây | 15 test, `tests/test_identity_ag02.py`, `evidence/AG02-report.md` |
| **AG-03 Admin/RBAC** | Vá 11 lỗ hổng (IDOR thu hồi phiên, di chuyển Super Admin qua ban, scope cho mọi non-super, fail-open scope, leo thang ma trận quyền, FK `.use`, archived hồi sinh, cross-tenant ban, rò audit…) | 20 test, `tests/test_admin_ag03.py`, `evidence/AG03-report.md` |
| **AG-04 Brain** | Fix `.env` quote, bridge tự cấp `tong-hop/doc` cho shadow, backfill có điều kiện, mapping fail-closed, E2E thật first-time/backfill/revoke/MFA | 14 test, `tests/test_brain_ag04.py`, `evidence/AG04-report.md`, `AG04-e2e.json` |
| **AG-05 QA** | Script nghiệm thu HTTP thật; **8/8 bước PASS, 6/6 bảo mật PASS, 0 FAIL, 0 BLOCKED** | 7 test, `scripts/acceptance.py`, `tests/test_e2e_ag05.py`, `evidence/AG05-report.md` |
| **Controller + MFA** | IP sau proxy, logout thu hồi Brain, handler 404 HTML, chặn tenant B sửa cấu hình toàn cục, dọn scope khi lưu trữ, khoá lựa chọn `.use` không tồn tại, test controller, chạy lại SSO/chat/revoke/MFA độc lập | 18 test, `tests/test_controller_ops.py`, `tests/test_mfa_controller.py`, `evidence/controller-*` |

**Không làn nào sửa Brain production, Caddy/DNS, hay push/deploy.**

---

## 5. BẰNG CHỨNG NGHIỆM THU

### 5.1. E2E 8 bước (AG-05)
- B1 đăng nhập `anh-thanh` · B2 tạo admin · B3 admin tạo nhân viên Ban Kinh doanh · B4 nhân viên đăng nhập · B5 chỉ 5 module, route admin 403 · B6 SSO Brain ticket one-time · B7 chat local thật · B8 thu hồi → COWORK 403 + Brain 401.
- Chi tiết: `evidence/AG05-acceptance.json`, `AG05-report.md`.

### 5.2. Nghiệm thu cuối (sau restart, bản tích hợp)
- AG-05: **8/8 PASS · 6/6 security PASS · 0 FAIL · 0 BLOCKED** lúc 17:53:03–17:53:07.
- B7: `providerId=local`, `nhan=real`, model `qwen2.5:7b-instruct`, `doTreMs=3682`, token 62/271, `chiPhi=0.0`, task `T-G02-000026`, trả lời 549 ký tự (metadata local/real là bằng chứng; model tự mô tả là Qwen/Alibaba không đổi bản chất local).
- Controller độc lập: `nhan-vien-final-01` → SSO 303 → `/api/auth/toi` 200 → chat 200 (`providerId=local`, `nhan=real`, model `qwen2.5:7b-instruct`, task mới) → thu hồi COWORK 403 + Brain 401 → cấp lại 200.
- Tệp: `evidence/FINAL-acceptance-20261019.json`, `FINAL-acceptance-report-20261019.md`, `controller-final-e2e.json`.

### 5.3. Chat AI Local thật
```
providerId=local · nhan=real · model=qwen2.5:7b-instruct
task=T-G02-000026 (nghiệm thu cuối) · token 62/160 · chiPhi=0 · traLoi 549 ký tự
```
- Task staging: `T-G02-000003`, `T-G02-000021`, `T-G02-000022`, `T-G02-000023` đều `local/real/qwen2.5:7b-instruct`, chi phí 0.
- Không dùng MOCK/cloud để báo PASS.

### 5.4. Thu hồi quyền
```
COWORK /brain trước: 200 → sau: 403 → cấp lại: 200
Brain /api/auth/toi trước: 200 → sau: 401
```
- `evidence/controller-revocation.json`, `AG04-revoke-nv01.json`.

### 5.5. MFA
- COWORK: TOTP đã triển khai; smoke production bật MFA cho admin tạm, logout, login mật khẩu → `/dang-nhap/mfa`, nhập TOTP → `/`, `/api/me` 200. Owner production chưa bật.
- Brain: `anh-thanh` mở Brain qua COWORK bị **403 “Chưa bỏ MFA cho tài khoản này”**, không set cookie, không tạo shadow; `COWORK_BRIDGE_ALLOW_MFA_USERS=0` giữ nguyên.
- `evidence/controller-mfa-guard.html`, `AG04-report.md` mục f.

### 5.6. Brain production không bị chạm
- Snapshot 19/10/2026: host `vip-ai-studio`, health 200, DB integrity `ok`, 7 user, 1 tenant, port 8899/8892 trên Studio **không mở**.
- `evidence/controller-production-snapshot-20261019.txt`.

---

### 5.7. Diễn tập rollback & validate Caddy (19/10/2026)
- `./scripts/rollback-drill.sh`: **PASS** — backup 17 user/275 audit integrity `ok`; restore counts khớp; server trên DB khôi phục cổng 8902 đăng nhập `anh-thanh` PASS, 15 module; xoá DB tạm.
- Caddy block `cowork`: **đã áp dụng**, `caddy validate` **Valid configuration**, reload OK; cert Let’s Encrypt hạn 17/01/2027; hash `be7a8ef8…5434`.

---

## 6. TÊN MIỀN & TRIỂN KHAI

| Hạng mục | Trạng thái |
|---|---|
| DNS `cowork.vipgroup.com.vn` | ✅ A → `160.22.170.20`; không cần đổi |
| DNS `ai.vipgroup.com.vn` | ✅ giữ nguyên |
| Caddy block `cowork` | ✅ đã áp dụng 19/10/2026; validate/reload OK; backup đã lưu |
| TLS `cowork` | ✅ Let’s Encrypt `CN=cowork.vipgroup.com.vn`, hạn 17/01/2027 |
| Tunnel COWORK `18835` | ✅ đang chạy, tách khỏi `18834` của Brain |
| Brain bridge production | ✅ đã áp dụng; bridge bật, MFA giữ nguyên |

**Ba cổng cần chủ dự án duyệt:**
1. COWORK lên Mac Studio (LaunchAgent, DB riêng).
2. Tunnel 18835 + Caddy + TLS.
3. Bridge Brain production (sau cùng, có rollback).

Chi tiết: `docs/TRIEN-KHAI-PRODUCTION.md`; rollback: `docs/ROLLBACK.md`.

---

## 7. VIỆC CHỦ DỰ ÁN CẦN LÀM

1. Mở production:
   - COWORK `https://cowork.vipgroup.com.vn`
   - Brain `https://ai.vipgroup.com.vn`
   - Mật khẩu owner: `ssh vip-ai-studio 'cat ~/VIP-AI/cowork/secrets/owner-anh-thanh.txt'` (file 0600).
2. Làm 8 bước theo `docs/NGHIEM-THU.md` trên production (3 cửa sổ riêng cho Super Admin / Quản trị / Nhân viên).
3. Ký bảng PASS/FAIL trong `docs/NGHIEM-THU.md`.
4. Quyết định MFA COWORK và việc bật `COWORK_BRIDGE_ALLOW_MFA_USERS=1` cho tài khoản owner đang MFA.
5. Theo dõi backup 03:20 hằng ngày; xem xét offsite backup COWORK.

---

## 8. RỦI RO / KHOẢNG TRỐNG CÒN LẠI

| Rủi ro | Mức | Xử lý |
|---|---|---|
| COWORK MFA đã có nhưng owner chưa bật | Trung bình | Bật tại `/ho-so/mfa`; CLI `mfa-reset` là break-glass |
| MFA owner chặn mở Brain qua COWORK | Có chủ đích | Giữ `ALLOW_MFA_USERS=0` tới khi chủ dự án nghiệm thu COWORK |
| Offsite backup COWORK chưa cài job | Trung bình | Script + test PASS; cài LaunchAgent/Full Disk Access thủ công |
| Access log ghi ticket query | Thấp | Ticket one-time/TTL 60s; tắt/lọc log hoặc chuyển POST khi lên thật |
| MFA secret staging thiếu | Thấp | Chỉ ảnh hưởng login trực tiếp staging; bridge vẫn chặn đúng |
| `sessions.ip` sau proxy | Thấp | Rate limit/audit đã dùng IP thật; cột phiên có thể vẫn 127.0.0.1 |
| Quota staging `tong-hop=100` | Thấp | Dữ liệu staging; production không đổi |
| Admin/manager COWORK không còn là Brain `quan-tri` | Có chủ đích | Fail-closed; muốn quyền Brain admin phải cơ chế riêng |

---

## 9. BÀN GIAO

| Tệp / thư mục | Nội dung |
|---|---|
| `README.md` | Chạy local, tài khoản test, kiến trúc |
| `docs/BAO-CAO-KHAO-SAT.md` | Khảo sát hiện trạng |
| `docs/CAU-HINH-TEN-MIEN.md` | DNS/Caddy/TLS + khối soạn sẵn |
| `docs/TRIEN-KHAI-PRODUCTION.md` | Kế hoạch 3 cổng |
| `docs/ROLLBACK.md` | Quay lui từng lớp |
| `docs/NGHIEM-THU.md` | 8 bước chủ dự án |
| `docs/MA-TRAN-YEU-CAU.md` | Truy vết yêu cầu → code → test |
| `docs/PRODUCTION-READINESS.md` | Checklist & khoảng trống |
| `docs/AGENT-CONTRACTS.md` | Hợp đồng 5 làn, API contract |
| `evidence/` | Ảnh, JSON, log, báo cáo 5 agent + controller |
| `deploy/` | LaunchAgent, tunnel, Caddy block (đã dùng cho go-live) |

**Production đã được triển khai ngày 19/10/2026 theo phê duyệt “cả 3 cổng” của chủ dự án; biên bản tại `evidence/PRODUCTION-DEPLOY-20261019.md`.**

- Bằng chứng: `evidence/FINAL-rollback-drill.txt`, `evidence/FINAL-caddy-validate.txt`.
