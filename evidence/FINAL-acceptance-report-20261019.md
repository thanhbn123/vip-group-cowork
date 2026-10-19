# AG-05 — BÁO CÁO NGHIỆM THU COWORK & BRAIN STAGING

**Thời điểm:** 2026-10-19T17:53:03+07:00 → 2026-10-19T17:53:07+07:00  ·  **Run tag:** `20261019-175303`
**Môi trường:** COWORK `http://127.0.0.1:8899` · Brain `http://127.0.0.1:8892` · DB `/Users/viporder/Library/CloudStorage/SynologyDrive-Macbook/VIP GROUP ID/cowork/data/cowork.db`
**Chế độ:** HTTP thật, mỗi người một cookie jar, không mock, không chạm Brain production 8891.
**Tệp bằng chứng:** `evidence/AG05-acceptance.json` · `evidence/AG05-run.log`

## 1. Tổng hợp

| Hạng mục | PASS | FAIL | BLOCKED |
|---|---|---|---|
| 8 bước nghiệm thu | 8 | 0 | 0 |
| Kiểm thử bảo mật | 6 | 0 | 0 |

**Kết luận:** PASS toàn bộ

## 2. Tám bước nghiệm thu

| Bước | Nội dung | Kết quả | HTTP | Ghi chú |
|---|---|---|---|---|
| B1 | Chủ sở hữu đăng nhập COWORK | PASS | GET /dang-nhap=200; POST /dang-nhap=303; GET /api/me=200 | — |
| B2 | Tạo quản trị cấp dưới mới (qa-admin-*) | PASS | GET /tai-khoan/tao-moi=200; POST /tai-khoan/tao-moi=200; GET /tai-khoan/qa-admin-20261019-175303=200 | — |
| B3 | Quản trị tạo nhân viên Ban Kinh doanh (qa-emp-*) | PASS | GET /dang-nhap=200; POST /dang-nhap=303; GET /api/me=200; GET /api/me=200; GET /tai-khoan/tao-moi=200; POST /tai-khoan/tao-moi=200; GET /tai-khoan/qa-emp-20261019-175303=200 | — |
| B4 | Nhân viên đăng nhập | PASS | GET /dang-nhap=200; POST /dang-nhap=303; GET /api/me=200; GET /api/me=200 | — |
| B5 | Nhân viên chỉ thấy module được cấp | PASS | GET /=200; GET /module/tasks=200; GET /module/knowledge=200; GET /module/usage=200; GET /tai-khoan=403; GET /ban=403; GET /vai-tro=403; GET /nhat-ky=403; GET /cai-dat=403; GET /phan-quyen=403; GET /module-registry=403 | — |
| B6 | Mở VIP AI Brain từ COWORK (SSO ticket) | PASS | GET /brain=200; POST /brain/mo=303; GET http://127.0.0.1:8892/cowork/vao?ticket=***=303; GET http://127.0.0.1:8892/api/auth/toi=200; GET http://127.0.0.1:8892/cowork/vao?ticket=***=401 | — |
| B7 | Chat thật với AI Local (local/real) | PASS | POST http://127.0.0.1:8892/api/chat=200 | — |
| B8 | Thu hồi quyền Brain + phiên Brain cũ | PASS | GET /ho-so=200; POST /tai-khoan/qa-emp-20261019-175303/phan-quyen=303; GET /brain=403; GET /ho-so=200; POST /brain/mo=403; GET http://127.0.0.1:8892/api/auth/toi=401 | — |

## 3. Kiểm thử bảo mật E2E

| Mã | Nội dung | Kết quả | HTTP | Ghi chú |
|---|---|---|---|---|
| S1 | Không cookie → 303/401 | PASS | GET /=303; GET /api/me=401; GET /tai-khoan=303 | — |
| S2 | Thiếu/sai CSRF → 403 | PASS | POST /tai-khoan/tao-moi=403; POST /tai-khoan/tao-moi=403; GET /ho-so=200; POST /ho-so=403 | — |
| S3 | Nhân viên gọi route quản trị → 403 | PASS | GET /tai-khoan=403; GET /ban=403; GET /vai-tro=403; GET /nhat-ky=403; GET /cai-dat=403; GET /phan-quyen=403; GET /module-registry=403; GET /ho-so=200; POST /tai-khoan/qa-admin-20261019-175303/khoa=303 | — |
| S4 | Cross-tenant: b-admin không đọc được anh-thanh → 404 | PASS | GET /dang-nhap=200; POST /dang-nhap=303; GET /api/me=200; GET /api/me=200; GET /tai-khoan/anh-thanh=404; GET /ho-so=200; POST /tai-khoan/anh-thanh/khoa=404; GET /tai-khoan=200 | — |
| S5 | Phiên bị thu hồi → 303 /dang-nhap | PASS | GET /ho-so=200; POST /tai-khoan/qa-admin-20261019-175303/thu-hoi-phien=303; GET /=303; GET /api/me=401 | — |
| S6 | Cổng bridge Brain fail-closed | PASS | GET http://127.0.0.1:8892/cowork/vao=400; POST http://127.0.0.1:8892/api/cowork/thu-hoi=401 | — |

## 4. Phần BLOCKED / FAIL

- Không có.

## 5. Dọn tài khoản QA
```json
{
  "batDau": "2026-10-19T17:53:07+07:00",
  "taiKhoan": {
    "admin": {
      "id": "qa-admin-20261019-175303",
      "hanhDong": [
        {
          "thuHoiPhien": 303
        },
        {
          "luuTru": 303
        }
      ],
      "trangThaiSau": "archived",
      "ketQua": "PASS"
    },
    "employee": {
      "id": "qa-emp-20261019-175303",
      "hanhDong": [
        {
          "thuHoiPhien": 303
        },
        {
          "luuTru": 303
        }
      ],
      "trangThaiSau": "archived",
      "ketQua": "PASS"
    }
  },
  "ketThuc": "2026-10-19T17:53:07+07:00",
  "ghiChu": "Tài khoản QA đã lưu trữ (archived), không xoá cứng; bản ghi audit còn nguyên."
}
```

## 6. Ghi chú kỹ thuật
- Brain staging health: `{"http": 200, "data": {"phienBan": "g02", "gio": "2026-10-19T17:53:03+07:00", "db": "ok"}, "ok": true}`
- COWORK health: `{"http": 200, "data": {"app": "cowork", "version": "1.0.0", "db": "ok", "brain": "bat", "gio": "2026-10-19T17:53:03+07:00"}}`
- Mật khẩu QA sinh trong bộ nhớ, không ghi ra đĩa; tài khoản QA được **lưu trữ** (archived), không xoá cứng.
- B7 chỉ PASS khi `providerId=local` **và** `nhan=real`; mọi trường hợp mock/cloud bị đánh FAIL.
- Không sửa mã ứng dụng, template, auth, services, brain hay script khác (đúng vùng sở hữu AG-05).

**Lưu ý an toàn:**
- POST quản trị bị từ chối ở tầng nghiệp vụ trả 303 + flash lỗi (quy ước routers/accounts.py); GET route quản trị trả 403.
- Brain staging (uvicorn access log) ghi ticket trong query string — ticket dùng một lần, TTL 60 giây; nên tắt/che access log khi lên thật.

## 7. Chi tiết bước PASS

### B1 — Chủ sở hữu đăng nhập COWORK
```json
{
  "nguoiDung": "anh-thanh",
  "vaiTro": "super_admin",
  "tenantId": "vip-group",
  "soModule": 15,
  "cookie": {
    "ten": "cowork_session",
    "httpOnly": true,
    "sameSite": "lax",
    "giaTri": "***"
  },
  "matKhauNguon": "secrets/owner-anh-thanh.txt"
}
```
### B2 — Tạo quản trị cấp dưới mới (qa-admin-*)
```json
{
  "id": "qa-admin-20261019-175303",
  "vaiTro": "admin",
  "ban": "ban-dieu-hanh",
  "trangThai": "active",
  "phamVi": "tenant (admin_scopes.department_id=NULL)",
  "xacMinhDb": true,
  "xacMinhHttp": 200,
  "matKhau": {
    "giaTri": "***",
    "doDai": 22,
    "luuO": "bộ nhớ tiến trình, không ghi đĩa"
  }
}
```
### B3 — Quản trị tạo nhân viên Ban Kinh doanh (qa-emp-*)
```json
{
  "id": "qa-emp-20261019-175303",
  "vaiTro": "employee",
  "ban": "kinh-doanh",
  "nguoiTao": "qa-admin-20261019-175303",
  "trangThai": "active",
  "xacMinhDb": true,
  "xacMinhHttp": 200,
  "matKhau": {
    "giaTri": "***",
    "doDai": 22
  }
}
```
### B4 — Nhân viên đăng nhập
```json
{
  "nguoiDung": "qa-emp-20261019-175303",
  "vaiTro": "employee",
  "ban": "Ban Kinh doanh",
  "modules": [
    "dashboard",
    "brain",
    "tasks",
    "knowledge",
    "usage"
  ],
  "soPhienMoi": 1
}
```
### B5 — Nhân viên chỉ thấy module được cấp
```json
{
  "apiMeModules": [
    "dashboard",
    "brain",
    "tasks",
    "knowledge",
    "usage"
  ],
  "sidebarHrefs": [
    "/",
    "/brain",
    "/module/knowledge",
    "/module/tasks",
    "/module/usage"
  ],
  "khopSidebar": true,
  "soMucQuanTriTrongSidebar": 0,
  "routeQuanTriBiChan": {
    "/tai-khoan": 403,
    "/ban": 403,
    "/vai-tro": 403,
    "/nhat-ky": 403,
    "/cai-dat": 403,
    "/phan-quyen": 403,
    "/module-registry": 403
  },
  "modulesTruyCapDuoc": [
    "/",
    "/brain",
    "/module/tasks",
    "/module/knowledge",
    "/module/usage"
  ]
}
```
### B6 — Mở VIP AI Brain từ COWORK (SSO ticket)
```json
{
  "coworkPage": 200,
  "postMoBrain": 303,
  "redirect": "http://127.0.0.1:8892/cowork/vao?ticket=***",
  "bridgeVao": 303,
  "brainToi": {
    "http": 200,
    "userId": "qa-emp-20261019-175303",
    "vaiTro": "thanh-vien",
    "tenantId": "vip-group"
  },
  "dangNhapLanHai": 0,
  "goiBrainTrongPhien": 2,
  "ticketDungMotLan": {
    "http": 401,
    "ketLuan": "không tái sử dụng được"
  },
  "cookiePhienBrain": {
    "ten": "vip_session",
    "giaTri": "***"
  }
}
```
### B7 — Chat thật với AI Local (local/real)
```json
{
  "prompt": "Xin chào VIP AI Brain. Hãy xác nhận mô hình AI Local đang xử lý yêu cầu này và cho tôi biết những chức năng hiện có thể sử dụng.",
  "providerId": "local",
  "nhan": "real",
  "meta": {
    "provider": "local",
    "model": "qwen2.5:7b-instruct",
    "doTreMs": 3682,
    "tokenVao": 62,
    "tokenRa": 271,
    "chiPhi": 0.0,
    "giaCo": false
  },
  "router": {
    "provider": "local",
    "luat": null,
    "lyDo": "Người dùng ép chọn"
  },
  "taskId": "T-G02-000024",
  "doDaiTraLoi": 961,
  "traLoiTrich": "Xin chào! Tôi xin được giới thiệu rằng tôi là Qwen, một trợ lý AI do Alibaba Cloud phát triển. Tôi có thể hỗ trợ bạn với nhiều chức năng khác nhau. Tuy nhiên, về mặt kỹ thuật, tôi không xác định được liệu yêu cầu của bạn có được xử lý bởi mô hình AI Local hay không, vì thông tin này không nằm trong phạm vi tôi có thể truy cập.\n\nTuy nhiên, tôi có thể hỗ trợ bạn với các chức năng sau:\n\n1. **Trả lời ",
  "biChan": 0
}
```
### B8 — Thu hồi quyền Brain + phiên Brain cũ
```json
{
  "thoiDiemThuHoi": "2026-10-19T17:53:07+07:00",
  "nguoiThucHien": "anh-thanh (super_admin)",
  "hinhThuc": "thu hồi quyền module brain (user_permissions deny)",
  "dbQuyen": [
    {
      "permission_code": "brain.use",
      "effect": "deny"
    },
    {
      "permission_code": "brain.view",
      "effect": "deny"
    }
  ],
  "coworkBrain": 403,
  "coworkBrainMo": 403,
  "brainToiSauThuHoi": 401,
  "phienBrainCu": "không truy cập được (401)"
}
```
