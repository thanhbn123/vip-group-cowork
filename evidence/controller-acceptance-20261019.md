# BIÊN BẢN NGHIỆM THU KỸ THUẬT — CONTROLLER

**Ngày:** 19/10/2026 · **Môi trường:** LOCAL/STAGING (không phải production)
**COWORK:** `http://127.0.0.1:8899` · **Brain staging:** `http://127.0.0.1:8892` · **AI:** Ollama Mac Studio qua tunnel
**Người chạy:** Master Project Controller (DeepSeek) · **Chủ dự án nghiệm thu:** anh-thanh (chưa ký)

> Đây là nghiệm thu **kỹ thuật** của controller, không thay thế nghiệm thu thực tế của chủ dự án.
> Không dùng MOCK. Chat Brain trả `providerId=local`, `nhan=real`, task ghi model thật.

---

## 1. KẾT QUẢ 8 BƯỚC

| # | Bước | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | `anh-thanh` đăng nhập COWORK | ✅ 303 → dashboard, 15 module | `evidence/screens/01-dashboard.png` |
| 2 | Tạo quản trị cấp dưới | ✅ `quan-tri-01` tạo qua UI, scope toàn tenant | `evidence/screens/02-accounts.png`, audit `account.create` |
| 3 | Quản trị tạo nhân viên theo ban | ✅ `nhan-vien-01` (Ban Kinh doanh) | audit actor `quan-tri-01` |
| 4 | Nhân viên đăng nhập | ✅ 303 → dashboard nhân viên | `evidence/AG01-screens/24-employee-dashboard.png` |
| 5 | Chỉ thấy module được cấp | ✅ đúng 5 module: dashboard, brain, tasks, knowledge, usage; route admin 403 | `/api/me`; ảnh 403 |
| 6 | Mở VIP AI Brain từ COWORK | ✅ `nhan-vien-ctrl-02` (user mới hoàn toàn): `/brain/mo` 303 → Brain `/cowork/vao` 303 → `/api/auth/toi` 200 đúng user | `evidence/controller-sso-chat.json` |
| 7 | AI Local trả lời thật | ✅ `POST /api/chat` 200; `providerId=local`, `nhan=real`; task `T-G02-000003` model `qwen2.5:7b-instruct`, chi phí 0.0 | `evidence/controller-sso-chat.json` + DB staging |
| 8 | Thu hồi quyền bị chặn | ✅ COWORK `/brain` 403; phiên Brain cũ `/api/auth/toi` 401; cấp lại 200 | `evidence/controller-revocation.json` |

---

## 2. KIỂM TRA BẢO MẬT BỔ SUNG

| Ca | Kết quả | Bằng chứng |
|---|---|---|
| MFA guard: `anh-thanh` mở Brain qua COWORK | ✅ **403** “Chưa bỏ MFA cho tài khoản này”; không tạo phiên | `evidence/controller-mfa-guard.html` |
| Quản trị cấp dưới tạo Super Admin | ✅ 400, chặn tại service | `tests/test_cowork.py::test_quan_tri_khong_tao_duoc_super_admin` |
| Quản trị cấp dưới sửa Super Admin | ✅ 303 + DB không đổi | `test_quan_tri_khong_sua_duoc_super_admin` |
| Quản trị scope ban thao tác ngoài ban | ✅ 400 “ngoài phạm vi” | `test_quan_tri_theo_ban_khong_thao_tac_ngoai_pham_vi` |
| Tenant B đọc tenant A | ✅ 404/không thấy | `test_cach_ly_tenant` |
| Thiếu CSRF | ✅ 403, không tạo user | `test_thieu_csrf_bi_chan` |
| Thu hồi phiên COWORK | ✅ request sau 303 `/dang-nhap` | `test_thu_hoi_phien_chan_ngay` |
| Audit append-only | ✅ UPDATE/DELETE bị trigger chặn | `test_audit_append_only` |
| Ticket Brain dùng lại | ✅ lần 2 → 401 | `test_brain_ticket_dung_mot_lan_va_hmac` |
| Mật khẩu chỉ lưu hash | ✅ scrypt + salt | `test_mat_khau_chi_luu_dang_bam` |

**Bộ test lõi:** `14 passed` (trước khi 5 agent bổ sung thêm test).

---

## 3. BẰNG CHỨNG CHAT LOCAL (TRÍCH)

```json
{
  "chat_ok": true,
  "providerId": "local",
  "nhan": "real",
  "metadata": null,
  "loi": null
}
```

Task trong `vip-brain-staging.db`:
```
id=T-G02-000003 · providerId=local · moHinh=qwen2.5:7b-instruct · nhan=real
chiPhi=0.0 · trangThai=completed
```

Nội dung trả lời bắt đầu: “Xin chào! Tôi là Qwen, một trợ lý AI do Alibaba Cloud phát triển…”
→ là model local trên Mac Studio, không phải cloud; chi phí 0.

---

## 4. BẰNG CHỨNG THU HỒI

```json
{
  "open_before": 200,
  "brain_toi_before": 200,
  "revoke_changes": {"brain": {"truoc": "default", "sau": "block"}},
  "cowork_brain_after": 403,
  "brain_toi_after": 401,
  "restore_changes": {"brain": {"truoc": "block", "sau": "default"}},
  "cowork_brain_restored": 200
}
```

→ Thu hồi quyền có hiệu lực **ngay** ở cả COWORK và phiên Brain native.

---

## 5. GIỚI HẠN CỦA BIÊN BẢN

- Chưa chạy trên tên miền chính thức `cowork.vipgroup.com.vn`; Caddy chưa có site block.
- Chưa áp bridge lên Brain production; chỉ staging bản sao.
- Chưa có MFA cho COWORK (chỉ mật khẩu); xem `docs/PRODUCTION-READINESS.md`.
- Chưa xử lý IP thật sau proxy Caddy.
- Chủ dự án chưa ký nghiệm thu; các bước thao tác tay theo `docs/NGHIEM-THU.md`.

---

## 6. KẾT LUẬN KỸ THUẬT

- Lõi ID/RBAC/tenant/audit/session: **ĐẠT** trong phạm vi local.
- Cầu nối COWORK → Brain: **ĐẠT** về ticket, phiên native, chat local thật, thu hồi.
- MFA Brain vẫn bảo vệ tài khoản `anh-thanh`: **ĐẠT** (chốt 403 có chủ ý).
- Production: **CHƯA TRIỂN KHAI**, đang chờ phê duyệt cổng 1–3 và nghiệm thu chủ dự án.
