# HỢP ĐỒNG 5 LÀN CODE AGENT — VIP GROUP COWORK

**Ngày:** 19/10/2026 · **Controller:** DeepSeek · **Baseline Git:** `8783b3b`
**Nguyên tắc:** không làm lại phần đã có; mỗi làn sở hữu tệp riêng; controller tích hợp.

---

## 0. TRẠNG THÁI XUẤT PHÁT (ĐÃ CÓ, KHÔNG XÂY LẠI)

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| COWORK FastAPI + SQLite | ✅ chạy `127.0.0.1:8899` | `/api/health` |
| Đăng nhập ID, scrypt, phiên máy chủ, CSRF, rate limit | ✅ | `cowork/auth.py`, 14 test |
| 5 vai trò, quyền module, chống leo thang, tenant | ✅ | `cowork/rbac.py`, `cowork/services.py` |
| Màn hình: dashboard, tài khoản, ban, vai trò, quyền, module, nhật ký, cài đặt, Brain | ✅ | `cowork/templates/` |
| Audit append-only (trigger) | ✅ | `schema.py` |
| Cầu nối Brain: ticket one-time + HMAC + phiên native | ✅ code; staging đang lỗi `.env` | `brain-bridge/cowork_bridge.py` |
| Bộ test bảo mật | ✅ 14/14 | `.venv/bin/python -m pytest -q` |

**Tài khoản test hiện có trong DB local (không phải production):**
`anh-thanh` (super_admin, mật khẩu trong `secrets/owner-anh-thanh.txt`),
`quan-tri-01` / `Qt01!Passw0rd` (admin), `quan-tri-scope` / `Scope01!Pass` (admin scope Kinh doanh),
`nhan-vien-01` / `Nv01!Passw0rd` (employee, Ban Kinh doanh).
Tenant B: `b-admin` / `Badmin!Passw0rd`, `b-user` / `Buser!Passw0rd`.

---

## 1. DỊCH VỤ & CỔNG

| Dịch vụ | Cổng | Ghi chú |
|---|---|---|
| COWORK | `127.0.0.1:8899` | đang chạy, DB `data/cowork.db` |
| VIP AI BRAIN production | Mac Studio `127.0.0.1:8891` | **CẤM CHẠM** |
| VIP AI BRAIN staging | `127.0.0.1:8892` | bản sao DB, bridge bật |
| Ollama (qua SSH tunnel) | `127.0.0.1:11434` | model `qwen2.5:7b-instruct` |
| VPS Caddy | `160.22.170.20:443` | **CẤM SỬA** trong giai đoạn này |

**Tên miền chính thức:** COWORK `https://cowork.vipgroup.com.vn` · Brain `https://ai.vipgroup.com.vn`.
DNS đã trỏ VPS; **chưa** thêm site block Caddy cho COWORK. Không đổi DNS/public URL.

---

## 2. API CONTRACT BẤT BIẾN

### 2.1. Phiên COWORK
- Cookie: `cowork_session` (HttpOnly, SameSite=Lax, Secure khi HTTPS).
- CSRF: form field `_csrf` / header `X-Csrf-Token`, token nằm trong `sessions.csrf_token`.
- Quyền hiệu lực = `role_permissions` + `user_permissions.allow` − `user_permissions.deny`.
- Mọi route quản trị kiểm tra quyền **tại service**, không tin hidden field/URL.

### 2.2. Cầu nối Brain
| Việc | Chiều | Endpoint | Chữ ký |
|---|---|---|---|
| Đổi ticket lấy danh tính | Brain → COWORK | `POST /api/internal/brain/consume` | `HMAC-SHA256(secret, "brain->cowork." + ts + "." + body)` |
| Thu hồi phiên Brain | COWORK → Brain | `POST /api/cowork/thu-hoi` | `HMAC-SHA256(secret, "cowork->brain." + ts + "." + body)` |
| Mở Brain | Trình duyệt | `GET {BRAIN_PUBLIC}/cowork/vao?ticket=...` | ticket one-time, TTL 60s |
| Sức khoẻ Brain | COWORK → Brain | `GET /api/health` | không cần chữ ký |
| Sức khoẻ bridge | bất kỳ | `GET /api/cowork/suc-khoe` | chỉ khi `COWORK_BRIDGE_BAT=1` |

Header: `X-Cowork-Ts`, `X-Cowork-Sig`. Bí mật chia sẻ: `data/brain_secret.key` (0600),
nạp vào staging qua `COWORK_SHARED_SECRET`. **Không đổi tên header/canonical string** nếu không cập nhật cả hai phía.

### 2.3. Dữ liệu
- Schema COWORK version 1, bảng `meta.schema_version`.
- **Không tự thêm migration**; nếu cần, báo controller.
- Không ghi/xoá `vip-brain.db` production.
- Staging DB: `brain-staging/data/vip-brain-staging.db` (bản sao).

---

## 3. PHÂN VÙNG SỞ HỮU

| Làn | Được phép sửa | Cấm sửa (báo controller) |
|---|---|---|
| **AG-01 Frontend** | `cowork/templates/**`, `cowork/static/**`, `tests/test_ui_ag01.py`, `evidence/AG01-*` | routes, services, schema, auth |
| **AG-02 Identity** | `cowork/auth.py`, `cowork/security.py`, `tests/test_identity_ag02.py`, `evidence/AG02-*` | `web.py`, routes, schema, templates |
| **AG-03 Admin/RBAC** | `cowork/rbac.py`, `cowork/services.py`, `cowork/routers/accounts.py`, `cowork/routers/departments.py`, `cowork/routers/roles.py`, `tests/test_admin_ag03.py`, `evidence/AG03-*` | `auth.py`, `web.py`, schema, templates |
| **AG-04 Brain** | `brain-bridge/**`, `scripts/provision_brain_staging.sh`, `scripts/start-brain-staging.sh`, `scripts/stop-brain-staging.sh`, `scripts/apply_bridge.py`, `scripts/remove_bridge.py`, `cowork/brain.py`, `cowork/routers/brain_routes.py`, `brain-staging/**`, `evidence/AG04-*` | Brain production, Caddy/DNS, `cowork/services.py`, templates |
| **AG-05 QA** | `tests/test_e2e_ag05.py`, `scripts/acceptance.py`, `evidence/AG05-*` | toàn bộ mã ứng dụng (chỉ đọc) |
| **Controller** | `cowork/{main,web,db,schema,config,cli}.py`, `cowork/routers/{auth_routes,dashboard,settings_routes,modules,audit_routes,internal}.py`, `docs/**`, `README.md`, `run.sh`, `scripts/{bootstrap,backup}.sh` | — |

**Luật:** nếu một sửa đổi bắt buộc phải chạm tệp ngoài vùng sở hữu, **dừng và báo controller**; không tự sửa.

---

## 4. TEST & BẰNG CHỨNG

```bash
cd "/Users/viporder/Library/CloudStorage/SynologyDrive-Macbook/VIP GROUP ID/cowork"
.venv/bin/python -m pytest -q
```

- Mỗi làn thêm test vào tệp **riêng**; không sửa test của làn khác.
- Không dùng MOCK để kết luận PASS. Chat Brain phải có `providerId=local`, `nhan=real`, nội dung thật.
- Báo cáo cuối làn: tệp đã sửa, lệnh đã chạy, kết quả test, rủi ro còn lại.
- Không `git commit`, không `git push`, không deploy, không restart Brain production.
- Không in mật khẩu/bí mật/token vào báo cáo; chỉ nêu đường dẫn tệp.

---

## 5. LỖI ĐANG MỞ CẦN AG-04 XỬ LÝ

`brain-staging/.env` chứa đường dẫn có dấu cách nhưng không quote:
`VIP_BRAIN_DB=/Users/.../VIP GROUP ID/...` → khi `source .env` sinh lỗi `GROUP: command not found`.
Cần quote `VIP_BRAIN_DB`, `MFA_SECRET_FILE`, `PYTHONPYCACHEPREFIX` trong
`scripts/provision_brain_staging.sh`, sửa `.env` hiện có, rồi chạy `start-brain-staging.sh`.
Bridge đã import OK sau khi vá `apply_bridge.py`.

---

## 6. THỨ TỰ TÍCH HỢP

1. AG-04 làm Brain staging sống → báo controller.
2. AG-01/02/03 chạy test riêng, báo diff.
3. AG-05 chạy E2E sau khi 1–3 xong; nếu staging chưa sống, đánh dấu `BLOCKED`, không fake.
4. Controller review diff, chạy toàn bộ pytest, chụp lại màn hình, cập nhật tài liệu bàn giao.

---

## 7. KẾT QUẢ CUỐI (19/10/2026)

| Làn | Test | Báo cáo |
|---|---:|---|
| AG-01 Frontend | 6 | `evidence/AG01-report.md` |
| AG-02 Identity | 15 | `evidence/AG02-report.md` |
| AG-03 Admin/RBAC | 20 | `evidence/AG03-report.md` |
| AG-04 Brain | 14 | `evidence/AG04-report.md` |
| AG-05 QA | 7 | `evidence/AG05-report.md` |
| Controller + MFA | 21 | `tests/test_controller_ops.py` |
| **Tổng** | **97 passed** | `evidence/FINAL-pytest.log` |

- Nghiệm thu cuối: **8/8 bước PASS · 6/6 bảo mật PASS · 0 FAIL · 0 BLOCKED**.
- Không làn nào sửa Brain production/Caddy/DNS; không push/deploy/commit.
- Controller đã tích hợp, restart local, chạy lại acceptance sau tích hợp.
