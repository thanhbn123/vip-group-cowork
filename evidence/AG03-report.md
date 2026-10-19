# AG-03 — BÁO CÁO ADMIN & RBAC (kiểm thử đối kháng + vá tối thiểu)

**Ngày:** 19/10/2026 · **Làn:** AG-03 Admin & RBAC · **Dự án:** VIP GROUP COWORK
**Phạm vi sửa:** `cowork/rbac.py`, `cowork/services.py`, `cowork/routers/accounts.py`,
`cowork/routers/departments.py`, `cowork/routers/roles.py`, `tests/test_admin_ag03.py`,
`evidence/AG03-*`.
**Không sửa:** `auth.py`, `web.py`, `schema.py`, templates, Brain, `main.py`, tài liệu controller.
**Không** deploy/push/commit; **không** chạm Brain production.

---

## 1. KẾT QUẢ CHỐT

| Hạng mục | Kết quả |
|---|---|
| Test AG-03 mới | **20 test** trong `tests/test_admin_ag03.py` — **20 passed** |
| Toàn bộ suite | **81 passed** (`.venv/bin/python -m pytest -o addopts='' -q`) |
| Replay trước khi vá | **4 passed / 16 failed** trên bản HEAD của 5 tệp AG-03 |
| Schema | **Không đổi** — không cần migration cho các vá này |
| API cũ | Giữ nguyên route, form field, status code nghiệp vụ; không đổi contract |

Bằng chứng:
- `evidence/AG03-pytest.txt` — log full suite xanh.
- `evidence/AG03-before.txt` — 16 test an toàn thất bại trên mã cũ (4 test bảo vệ đã có sẵn).
- `evidence/AG03-diff.txt` — diff 5 tệp mã nguồn AG-03.

---

## 2. TỆP ĐÃ SỬA

| Tệp | Thay đổi chính |
|---|---|
| `cowork/rbac.py` | `pham_vi_ban` lọc tenant + kiểm tra ban thuộc tenant; `co_the_quan_ly` áp phạm vi cho **mọi** vai trò không phải Super Admin và chặn target `archived`; thêm `co_the_sua_vai_tro`. |
| `cowork/services.py` | Chặn tạo admin bởi non-super; `_luu_scope_admin` fail-closed; `dat_quyen_module` chỉ dùng mã quyền tồn tại + kiểm tra toàn bộ trước khi ghi; `cap_nhat_quyen_vai_tro` thêm cấp bậc/subset/quyền Super-only; `cap_nhat_ban` chặn di chuyển Super Admin/ngoài phạm vi; tenant guard cho ban; `tao_ban` báo Conflict thay vì 500; `doi_trang_thai` xoá `login_attempts` sai của target khi mở khoá; `thong_ke` không lộ audit toàn tenant cho người dùng thường; module/cài đặt chỉ Super Admin. |
| `cowork/routers/accounts.py` | Nút hành động phản ánh đúng quyền + cấp + phạm vi; danh sách ban trong form lọc phạm vi; **ràng buộc session_id thuộc đúng user + tenant** khi thu hồi một phiên; chặn xem ma trận quyền ngoài phạm vi. |
| `cowork/routers/departments.py` | Đóng connection ở `/ban/tao-moi`; lọc ứng viên trưởng ban theo cấp + phạm vi, loại Super Admin. |
| `cowork/routers/roles.py` | `co_sua` dùng `co_the_sua_vai_tro` (khớp service). |
| `tests/test_admin_ag03.py` | **Mới**, 20 test đối kháng. |

Không có thay đổi ngoài vùng sở hữu.

---

## 3. LỖ HỔNG ĐÃ TÌM & CÁCH VÁ

Mức: **C** = nghiêm trọng (leo thang/chiếm phiên), **H** = cao, **M** = trung bình.

| # | Mức | Lỗ hổng (tấn công thực tế) | Vá tối thiểu | Test |
|---|---|---|---|---|
| 1 | **C** | **IDOR thu hồi phiên**: `POST /tai-khoan/{user_id}/phien/{session_id}/thu-hoi` chỉ kiểm tra `user_id`, rồi thu hồi theo `session_id`. Admin có thể truyền user mình quản lý + session_id của **Super Admin / tenant khác** để đá phiên nạn nhân. | Truy vấn session phải khớp `id + user_id + tenant_id + status='active'`; không khớp thì không thu hồi, audit gắn target user thay vì lộ session ID ngoài tenant. | `test_thu_hoi_phien_phai_dung_chu_so_huu` |
| 2 | **C** | **Di chuyển Super Admin qua trưởng ban**: `cap_nhat_ban` chỉ kiểm tra cấp vai trò của ứng viên, không kiểm tra mình có được quản lý ứng viên đó không. Admin scope Kinh doanh gán `manager_user_id=anh-thanh` ⇒ đổi `department_id` của Super Admin; hoặc kéo admin/trưởng ban ban khác vào ban mình. | Gọi `co_the_quan_ly(..., "departments.update")` cho ứng viên trưởng ban (chặn Super Admin, khác cấp, ngoài phạm vi, archived). | `test_cap_nhat_ban_khong_di_chuyen_super_hoac_nguoi_ngoai_pham_vi` |
| 3 | **C** | **Bỏ phạm vi cho vai trò không phải admin/manager**: `co_the_quan_ly` chỉ áp `trong_pham_vi` khi actor là `admin`/`department_manager`. Nhân viên/đối tác được uỷ quyền `accounts.update`/`suspend`/`create` thao tác được trên **mọi người trong tenant**. | Áp `trong_pham_vi` cho mọi actor không phải Super Admin; vai trò không có phạm vi trả tập rỗng ⇒ fail-closed. | `test_employee_duoc_cap_quyen_khong_thao_tac_ngoai_ban` |
| 4 | **C** | **Tạo tài khoản ngoài ban**: `_kiem_tra_pham_vi_ban` cũng chỉ áp cho admin/manager. Nhân viên có `accounts.create` tạo được đối tác ở ban bất kỳ/không ban. | Áp phạm vi cho mọi non-super ở khâu tạo/sửa. | `test_employee_duoc_cap_quyen_khong_thao_tac_ngoai_ban` |
| 5 | **H** | **`_luu_scope_admin` fail-open**: nếu non-super tạo được admin, nhánh cũ `INSERT admin_scopes(..., NULL)` biến admin đó thành **toàn tenant**. | Non-super ⇒ `Forbidden`; thêm chốt chỉ Super Admin được tạo admin. | `test_admin_scope_null_va_khong_dat_pham_vi_cho_nguoi_khac` |
| 6 | **C** | **Sửa vai trò ngang cấp/leo thang qua ma trận quyền**: `cap_nhat_quyen_vai_tro` chỉ kiểm tra `roles.manage`. Nếu quyền này bị uỷ quyền, admin sửa được vai trò `admin` (ngang cấp), thêm `settings.manage`/`roles.manage`/quyền mình không có. Super cũng có thể gán quyền Super-only cho vai trò khác. | Bắt buộc vai trò **thấp hơn cấp** + có cả `roles.manage` và `permissions.grant`; mọi quyền thêm phải là subset của actor; quyền thu hồi cũng phải thuộc actor; cấm `QUYEN_CHI_SUPER` trên vai trò non-super; kiểm tra xong mới ghi. | `test_roles_manage_bi_uy_quyen_khong_sua_vai_tro_ngang_cap`, `test_super_khong_gan_duoc_quyen_chi_super_cho_vai_tro_khac` |
| 7 | **H** | **`.use` không tồn tại gây 500**: `dat_quyen_module` sinh `dashboard.use`/`accounts.use`… cho module không có quyền này ⇒ `FOREIGN KEY constraint failed`, và có thể **thu hồi dở dang** module trước khi bị từ chối module sau (DB autocommit). | Tra bảng `permissions`, chỉ ghi mã tồn tại; module không có `.use` thì "use" quy đổi "view", "block" chỉ deny mã tồn tại; kiểm tra toàn bộ lựa chọn trước khi xoá/ghi. | `test_bon_muc_quyen_khong_lam_500_module_khong_co_use`, `test_permissions_grant_subset_scope_va_nguyen_tu` |
| 8 | **H** | **Tài khoản archived bị hồi sinh**: admin bấm "Mở khoá" (hoặc gọi service) trên user đã lưu trữ ⇒ `status='active'`; sửa/reset/phân quyền trên archived vẫn được. | `co_the_quan_ly` chặn target `archived` với mọi non-super; Super Admin vẫn khôi phục được. | `test_tai_khoan_luu_tru_khong_bi_khoi_phuc_boi_admin` |
| 9 | **H** | **`admin_scopes` không lọc tenant**: scope đọc theo `user_id` không kiểm tra tenant/ban thuộc tenant ⇒ dữ liệu scope chéo tenant có thể mở phạm vi sai. | Join `departments` + lọc `tenant_id`; luôn kiểm tra `department_id` thuộc tenant khi ghi scope. | `test_cach_ly_tenant_nguoi_dung_ban_audit` |
| 10 | **M** | **Trùng mã ban cross-tenant gây 500**: `departments.id = code` là duy nhất toàn hệ thống nhưng chỉ kiểm tra theo tenant ⇒ tenant B tạo `kinh-doanh` bị `IntegrityError` 500. | Kiểm tra ID toàn cục, trả `Conflict` (400 ở form) thay vì 500. | `test_tao_ban_trung_ma_tenant_khac_khong_500` |
| 11 | **M** | **Rò rỉ audit toàn tenant**: `thong_ke` trả `auditHomNay` toàn tenant cho nhân viên không có `accounts.view`/`audit.view`. | Người dùng thường đếm `audit_log` theo `actor_id=user.id`; admin/audit-view giữ toàn tenant. | `test_thong_ke_audit_khong_ro_ri_tenant_cho_nhan_vien` |
| 12 | **M** | **Xem ma trận quyền ngoài phạm vi**: `GET /tai-khoan/{id}/phan-quyen` không kiểm tra phạm vi; trưởng ban xem được quyền của nhân sự ban khác/Super Admin. | Chặn target ngoài phạm vi; `co_cap` dùng đúng `co_the_quan_ly`. | `test_truong_ban_chi_thay_va_sua_trong_ban`, `test_admin_scope_chi_trong_ban` |
| 13 | **M** | **UI hứa hẹn thao tác trái phép**: nút reset/khoá/lưu trữ/thu hồi/quyền hiện trên Super Admin hoặc target ngoài phạm vi dù service chặn. | Các cờ `co_*` dùng `co_the_quan_ly` theo từng hành động; `ban_ds`/ứng viên trưởng ban lọc phạm vi. | `test_super_admin_khong_bi_thay_doi_boi_admin`, `test_truong_ban_chi_thay_va_sua_trong_ban` |
| 14 | **M** | **Mở khoá vẫn bị rate-limit**: 5 lần sai → admin mở khoá → đăng nhập đúng vẫn bị chặn vì `login_attempts` còn. | Khi chuyển `active`, xoá `login_attempts success=0` của **đúng target**, mọi IP; không xoá của người khác. | `test_mo_khoa_xoa_bo_dem_dang_nhap_sai_cua_target` |
| 15 | **M** | **Rò connection** `/ban/tao-moi` (`rbac.pham_vi_ban(db.connect(), ...)`). | Mở/đóng trong `try/finally`. | Kiểm tra qua full suite + review diff |
| 16 | **M** | `cap_nhat_module`/`cap_nhat_cai_dat` chỉ dựa vào permission; nếu dữ liệu cũ uỷ quyền `modules.manage`/`settings.manage`, non-super thao tác được. | Chốt `la_super(actor)` tại service (phòng thủ theo `QUYEN_CHI_SUPER`). | `test_module_va_cai_dat_chi_super` |

### Điểm đã có sẵn và được test xác nhận (không xây lại)
- Super Admin không bị sửa/khoá/lưu trữ/reset/phân quyền bởi admin/manager (test trực tiếp HTTP + service).
- Không tạo được Super Admin thứ hai qua UI/API (kể cả chính Super Admin).
- Admin không tự đổi vai trò/quyền/trạng thái của mình.
- Audit actor/target đúng và **không chứa mật khẩu** (quét toàn bộ `detail`).
- Tenant A/B tách biệt ở user, ban, danh sách, audit; session cross-tenant bị chặn sau vá.

---

## 4. QUYẾT ĐỊNH ARCHIVE (theo yêu cầu controller)

Role `admin` mặc định **không** có `accounts.archive`; chỉ Super Admin có toàn quyền.
Bài test `test_tai_khoan_luu_tru_khong_bi_khoi_phuc_boi_admin` chọn phương án **(a)**:
cấp bổ sung `accounts.archive` cho `admin-arch` **trong test** để kiểm luồng archive, rồi
chứng minh admin không thể mở khoá/sửa/reset/phân quyền tài khoản đã archived; Super Admin
vẫn khôi phục được. **Không** thêm `accounts.archive` vào ma trận role admin trong mã.

---

## 5. GHI CHÚ VỀ `admin_scopes`, LAST SUPER ADMIN, ARCHIVED

- **`admin_scopes` NULL** = toàn tenant (chỉ Super Admin được tạo). **Không có dòng** =
  chỉ ban của mình (mặc định đóng), không phải toàn tenant. Scope trỏ ban tenant khác bị bỏ qua.
- **Last Super Admin**: mọi luồng web/service đều chặn target có `role_code='super_admin'`
  (kể cả chính Super Admin khác), nên `dem_super_admin` luôn ≥ 1 trong phạm vi API/UI.
  Hàm `rbac.dem_super_admin` vẫn chưa được dùng; nếu tương lai cho phép tạm khoá Super Admin
  thì phải gọi hàm này trước khi đổi trạng thái.
- **Archived**: non-super fail-closed (không sửa/reset/phân quyền/mở khoá/thu hồi phiên);
  Super Admin vẫn có thể khôi phục. Tài khoản archived không đăng nhập được (auth đã chặn).

---

## 6. VIỆC CẦN CONTROLLER XỬ LÝ (ngoài vùng AG-03)

1. **Schema `departments.id` toàn cục**: hiện `id = code`, nên hai tenant không thể dùng
   cùng mã ban; đã đổi 500 → 409 nhưng muốn namespace theo tenant phải migration
   (`schema.py`/controller). Đề xuất ID ngẫu nhiên hoặc `(tenant_id, code)`.
2. **Roles/modules là bảng toàn cục**: Super Admin tenant B sửa ma trận role/module ảnh hưởng
   tenant A. AG-03 đã chặn non-super và quyền Super-only, nhưng không thể tách tenant nếu
   không đổi schema. Cần quyết định: role/module theo tenant hay chỉ tenant mặc định được quản lý.
3. **Settings lưu theo tenant mặc định**: `db.get_setting`/`set_setting` bỏ qua tenant; Super
   Admin tenant B có thể ghi cài đặt của tenant mặc định. Cần sửa `db.py`/`settings_routes.py`
   (controller) hoặc chấp nhận mô hình một tenant cấu hình chung.
4. **`tao_super_admin` (bootstrap CLI)** vẫn tạo/reset nhiều Super Admin ngoài UI/API. Cần quy
   trình vận hành bảo vệ CLI; nếu muốn “đúng một Super Admin” phải thêm kiểm tra ở CLI/service.
5. **Tạo role**: hiện **không có** route/service tạo role mới (chỉ sửa ma trận). Nếu bổ sung,
   phải dùng lại `co_the_sua_vai_tro` + kiểm tra subset/Super-only.
6. **Template module permissions** vẫn hiện lựa chọn "Sử dụng" cho module không có `.use`;
   service đã quy đổi an toàn thành "view". AG-01/controller có thể ẩn lựa chọn này cho rõ nghĩa.
7. **`thong_ke` còn `soBan` toàn tenant** cho người dùng thường (rò nhẹ số ban); chưa đổi vì
   ngoài phạm vi yêu cầu. Nếu muốn, lọc theo phạm vi tương tự audit.
8. **`modules.min_role_level` chưa được dùng** trong phân quyền hiệu lực (controller).
9. **`admin_scopes` của admin archived** chưa được dọn; không gây leo thang (đã fail-closed)
   nhưng nên dọn khi có luồng archive chuẩn.

---

## 7. LỆNH ĐÃ CHẠY

```bash
cd "/Users/viporder/Library/CloudStorage/SynologyDrive-Macbook/VIP GROUP ID/cowork"
.venv/bin/python -m compileall -q cowork
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -o addopts='' -q     # 81 passed
.venv/bin/python -m pytest --collect-only -o addopts='' -q tests/test_admin_ag03.py  # 20 tests
```

Replay trước vá: sao chép cây làm việc, trả 5 tệp AG-03 về `HEAD`, chạy
`tests/test_admin_ag03.py` → **4 passed / 16 failed**; log rút gọn ở `evidence/AG03-before.txt`.

**Không có mật khẩu/bí mật/token nào được in trong báo cáo này hoặc trong evidence.**
