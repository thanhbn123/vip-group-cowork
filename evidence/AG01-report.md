# AG-01 FRONTEND — BÁO CÁO HOÀN THIỆN GIAO DIỆN COWORK

**Ngày:** 19/10/2026 · **Làn:** AG-01 Frontend · **Trạng thái:** HOÀN THÀNH
**Phạm vi đã sửa:** `cowork/templates/**`, `cowork/static/**`, `tests/test_ui_ag01.py`, `evidence/AG01-*`.
Không sửa route, service, schema, auth, brain hay scripts khác.

---

## 1. Kết quả cuối

| Hạng mục | Kết quả |
|---|---|
| Test AG-01 | **6 passed** (`tests/test_ui_ag01.py`) |
| Toàn bộ pytest | **81 passed, 1 warning** — exit code 0 |
| Test bảo mật cũ | 14/14 vẫn xanh (nằm trong 81 test) |
| Màn hình chụp | 56 ảnh desktop 1440×1000 + mobile 390×844, thêm 1 ảnh menu mobile = **57 PNG** |
| Tràn ngang | **0** (`scrollWidth / innerWidth = 1.0` ở mọi màn hình) |
| Lỗi console ngoài dự kiến | **0** (4 message còn lại là HTTP 403/404 chủ đích của trang lỗi) |
| Link nội bộ 404/500 | **0** (crawl tự động trong test và Playwright) |
| Form POST thiếu `_csrf` | **0** (kiểm tra 20+ form trên toàn bộ màn hình) |
| Inline script/style/onclick | **0** trong 27 template và HTML render |

Lệnh đã chạy:

```bash
cd "/Users/viporder/Library/CloudStorage/SynologyDrive-Macbook/VIP GROUP ID/cowork"
.venv/bin/python -m pytest -q                                     # exit 0
.venv/bin/python -m pytest -o addopts="" -q                       # 81 passed
NODE_PATH="$HOME/code/veh4-g12-playwright/node_modules" \
  COWORK_OWNER_PASSWORD="$(cat secrets/owner-anh-thanh.txt)" \
  node evidence/AG01-capture.js                                   # exit 0
```

---

## 2. Tệp đã sửa / tạo

### Template
| Tệp | Thay đổi chính |
|---|---|
| `base.html` | Nút đóng menu mobile, `nav` có `aria-label`, hỗ trợ `inert` cho sidebar đóng |
| `dashboard.html` | Nhãn "Tài khoản của tôi" cho người không có `accounts.view`; nhân viên thấy "Sự kiện của tôi hôm nay" (backend đã scoped theo user) |
| `404.html` | Bỏ link chết `/tai-khoan` (nhân viên bị 403) → `/ho-so` |
| `accounts/list.html` | `data-label` cho cột, `scope="col"`, `aria-label` ô tìm kiếm, URL-encode tham số phân trang |
| `accounts/detail.html` | `data-label` cho bảng quyền và bảng phiên |
| `accounts/permissions.html` | `data-label` ngắn cho 4 lựa chọn, `aria-label` đầy đủ cho từng radio |
| `accounts/permissions_overview.html` | `data-label`, `scope`, `aria-label` ô tìm kiếm |
| `departments/detail.html` | `data-label` cho bảng nhân sự |
| `audit/list.html` | `data-label`, `aria-label` cho ô hành động/đối tượng |
| `profile.html` | `data-label` cho bảng phiên |
| `modules/list.html` | Ẩn nút bật/tắt với 3 module nền tảng (backend từ chối), thêm badge "nền tảng" |
| `login.html`, `change_password.html` | `aria-pressed="false"`, `aria-label` cụ thể cho nút hiện/ẩn mật khẩu |
| `settings.html` | Vùng kết quả kiểm tra Brain có `role="status"`, `aria-live="polite"` |
| Tất cả template có bảng | Thêm `scope="col"`; header thao tác trống có nhãn ẩn cho screen reader |

### Static
| Tệp | Thay đổi chính |
|---|---|
| `app.css` | `[hidden]{display:none!important}` (sửa lỗi field đối tác vẫn hiện); bảng dạng thẻ có nhãn ở ≤720px; ma trận quyền 4 lựa chọn gọn; module registry xếp dọc; thanh lưu không còn sticky che nội dung trên mobile; chống tràn chữ dài; nút đóng sidebar |
| `app.js` | Sidebar mobile dùng `inert` khi đóng, quản lý focus khi mở/đóng, nút đóng; cập nhật `aria-label`/`aria-pressed` khi hiện/ẩn mật khẩu |

### Test & bằng chứng
| Tệp | Nội dung |
|---|---|
| `tests/test_ui_ag01.py` | 6 test giao diện (mô tả ở mục 3) |
| `evidence/AG01-capture.js` | Script Playwright + Chrome hệ thống (`channel: "chrome"`) |
| `evidence/AG01-screens/*.png` | 57 ảnh bằng chứng |
| `evidence/AG01-screens/report.json` | Dữ liệu đo: status, overflow, console, a11y, `inert` |
| `evidence/AG01-report.md` | Báo cáo này |

---

## 3. Test đã thêm (`tests/test_ui_ag01.py`)

1. **`test_dang_nhap_ba_vai_tro_va_menu_theo_api_me`**
   - Đăng nhập thật `anh-thanh` (mật khẩu đọc từ `secrets/owner-anh-thanh.txt`), `quan-tri-01`, `nhan-vien-01`.
   - So khớp menu render với `/api/me`: Super Admin 15 module, Quản trị 13, Nhân viên **đúng 5** (`dashboard`, `brain`, `tasks`, `knowledge`, `usage`).
   - Nhân viên không thấy Tài khoản / Ban / Vai trò / Nhật ký / Cài đặt; 12 màn quản trị trả **403 HTML**.
2. **`test_crawl_link_noi_bo_khong_co_404_500`**
   - Crawl toàn bộ href nội bộ của 23 màn hình Super Admin + 7 màn hình nhân viên + trang 403/404; kiểm tra landmark, `lang="vi"`, `h1`, `data-label`, `scope`, không inline.
3. **`test_moi_form_post_deu_co_csrf`**
   - Mọi form POST (kể cả form đăng nhập khách) phải có `_csrf` khác rỗng; action nội bộ.
4. **`test_csp_chat_va_khong_inline_trong_template`**
   - Quét 27 template: không `<script>` inline, `<style>`, `style=`, `on*=`; CSP response phải có `script-src 'self'`, `style-src 'self'`, không `unsafe-inline`/`unsafe-eval`.
5. **`test_trang_loi_403_404_render_dung_va_khong_link_chet`**
   - 403/404 render template có mã lỗi, `<main>`, nav; trang 404 của nhân viên không mời vào `/tai-khoan`.
6. **`test_route_khong_ton_tai_phai_tra_ve_trang_404_html`**
   - Route lạ trả `404.html` (không còn JSON `{"detail":"Not Found"}`). Test này từng `xfail`, đã chuyển **PASS** sau khi controller thêm handler `StarletteHTTPException` trong `main.py`.

---

## 4. Kiểm tra giao diện bằng Playwright

- **Thiết bị:** Chrome hệ thống qua Playwright (`channel: "chrome"`), headless.
- **Viewport:** 1440×1000 (desktop) và 390×844 (mobile).
- **Đăng nhập:** `anh-thanh` (Super Admin), `nhan-vien-01` (Nhân viên), `quan-tri-01` (Quản trị).
- **Màn hình:** `/`, `/dang-nhap`, `/tai-khoan`, `/tai-khoan/tao-moi`, `/tai-khoan/nhan-vien-01`, `/tai-khoan/nhan-vien-01/phan-quyen`, `/phan-quyen`, `/ban`, `/ban/kinh-doanh`, `/vai-tro`, `/vai-tro/admin`, `/module-registry`, `/nhat-ky`, `/cai-dat`, `/brain`, `/ho-so`, `/doi-mat-khau`, 5 trang `/module/*`, `/doi-tac`, trang 403, trang 404.
- **Kết quả đo:**
  - `document.documentElement.scrollWidth === window.innerWidth` ở **56/56** màn hình.
  - **0** lỗi console/pageerror/requestfailed ngoài 4 message HTTP 403/404 chủ đích.
  - **0** phần tử `[hidden]` bị CSS hiển thị; **0** `<td>` thiếu `data-label`; **0** `<th>` thiếu `scope`; **0** input thiếu tên truy cập; **0** nút/link không có tên.
  - Menu mobile: khi đóng `sidebar[inert]`, khi mở `inert=false`, `aria-expanded="true"`, focus nằm trong sidebar.
- **Ảnh chính:**
  - `desktop-01-dashboard.png`, `desktop-02-accounts.png`, `desktop-04-account-detail.png`
  - `desktop-09-roles.png`, `desktop-10-role-admin.png`, `desktop-12-audit.png`
  - `mobile-02-accounts.png`, `mobile-04-account-detail.png`, `mobile-05-account-permissions.png`
  - `mobile-11-modules.png`, `mobile-12-audit.png`, `mobile-24-employee-dashboard.png`
  - `mobile-26-error-403.png`, `mobile-23-error-404.png`, `mobile-28-nav-open.png`

---

## 5. Lỗi backend phát hiện (không tự sửa)

1. **Route không khớp trả JSON 404** — `cowork/main.py` chưa bắt `StarletteHTTPException`.
   → **Đã được controller sửa trong phiên** (thêm handler, HTML cho trình duyệt / JSON cho API). Test AG-01 đã chuyển PASS.
   *Lưu ý vận hành:* tiến trình uvicorn đang chạy ở `127.0.0.1:8899` tại thời điểm đo vẫn là code cũ; cần restart COWORK để nhận handler mới.
2. **Rò rỉ số liệu dashboard** — `services.thong_ke` từng trả `auditHomNay` toàn tenant cho nhân viên không có `audit.view`.
   → **Đã được làn backend sửa** (đếm theo `actor_id` của chính người dùng). Giao diện dùng nhãn "Sự kiện của tôi hôm nay" cho người không có quyền audit.
3. **Rò rỉ connection** — `cowork/routers/departments.py`, nhánh `GET /ban/tao-moi` từng gọi
   `rbac.pham_vi_ban(db.connect(), user)` mà không đóng connection.
   → **Đã được controller sửa trong phiên** (bọc `try/finally` và đóng connection).
4. **Hai test AG-03 tạm đỏ giữa phiên** (FOREIGN KEY `dashboard.use`, quyền `accounts.archive`).
   → Đã được làn AG-03 xử lý; lần chạy cuối toàn bộ 81 test xanh.

Không có mật khẩu/bí mật/token nào được ghi vào báo cáo hoặc ảnh.

---

## 6. Rủi ro còn lại

- **Mới kiểm tra trên Chrome hệ thống**, chưa chạy Safari/Firefox. Các tính năng dùng `inert`, `:has()`, `dvh` không có; `inert` và `:has()` cần trình duyệt hiện đại (Chrome 105+, Safari 15.4+).
- **Breakpoint bảng dạng thẻ là ≤720px.** Ở 768px (tablet dọc) bảng vẫn dạng bảng nhưng có `overflow-x:auto`; chưa đo tràn ngang ở đúng 768px.
- Trang `/nhat-ky` và `/tai-khoan/{id}` trên mobile rất dài (bảng nhiều dòng chuyển thành thẻ). Nội dung đầy đủ, không cắt, nhưng cần cuộn nhiều.
- `[hidden]{display:none!important}` là luật toàn cục; nếu sau này có phần tử cần vừa `hidden` vừa hiển thị bằng CSS thì phải bỏ thuộc tính thay vì đè CSS.
- Uvicorn 8899 cần restart để nhận thay đổi `main.py` của controller (template/CSS đã tự nạp).
- Chưa kiểm tra in ấn (`@media print`) và chế độ tương phản cao của hệ điều hành.
