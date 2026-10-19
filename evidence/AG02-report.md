# AG-02 IDENTITY — Báo cáo làm cứng & kiểm thử đối kháng

**Ngày:** 19/10/2026 · **Làn:** AG-02 Identity · **Baseline:** `8783b3b` (làm việc trên cây hiện tại)
**Phạm vi:** chỉ `cowork/auth.py`, `cowork/security.py`, `tests/test_identity_ag02.py`, `evidence/AG02-*`.
**Trạng thái Identity:** giữ nguyên kiến trúc đã có (ID + mật khẩu scrypt, phiên máy chủ, CSRF,
rate limit, đổi/đặt lại mật khẩu, thu hồi phiên). Không xây Identity Provider thứ hai.

---

## 1. Tệp đã thay đổi

| Tệp | Loại | Nội dung |
|---|---|---|
| `cowork/auth.py` | sửa | 2 lỗi thật (mục 3), không đổi chữ ký hàm/API |
| `cowork/security.py` | không sửa | rà soát, không phát hiện lỗi cần sửa |
| `tests/test_identity_ag02.py` | tạo mới | 15 test đối kháng, dùng app + SQLite thật, không mock |
| `evidence/AG02-report.md` | tạo mới | báo cáo này |
| `evidence/AG02-pytest-full.log` | tạo mới | log `.venv/bin/python -m pytest -q` toàn bộ |
| `evidence/AG02-pytest-identity.log` | tạo mới | log 14 test cũ + 15 test AG-02 (`29 passed`) |

Không sửa `web.py`, route, schema, template, service, brain. Không git commit/push, không deploy,
không đụng Brain production.

---

## 2. Kết quả kiểm thử

### 2.1. Lệnh và kết quả

```bash
cd "/Users/viporder/Library/CloudStorage/SynologyDrive-Macbook/VIP GROUP ID/cowork"
.venv/bin/python -m pytest tests/test_cowork.py tests/test_identity_ag02.py
# 29 passed, 1 warning — log: evidence/AG02-pytest-identity.log (14 test cũ + 15 test mới)

.venv/bin/python -m pytest -q
# exit 0 — log: evidence/AG02-pytest-full.log
# 54 dấu "." tại thời điểm chạy: 14 test cũ + 15 AG-02 + 25 test của các làn khác
# (AG-04, AG-05, controller) đang được hoàn thiện song song trong cùng tests/.
```

Không có test nào bị skip/xfail; không dùng mock. Mọi test đi qua `TestClient` + DB SQLite tạm
(`conftest.py`) và các thao tác DB thật (đặt `expires_at`, `last_seen_at`, `users.status`,
`login_attempts`) như sự cố vận hành thật.

### 2.2. Bảng test đối kháng (15 test)

| # | Test | Kịch bản đối kháng | Kỳ vọng | KQ |
|---|---|---|---|---|
| 1 | `test_token_phien_gia_bi_tu_choi` | Cookie token bịa đúng định dạng, **token_hash trong DB**, ID phiên, token Bearer bịa | 303 về `/dang-nhap`; `/api/me` 401; không sinh phiên mới | PASS |
| 2 | `test_token_cu_sau_dang_xuat_bi_tu_choi` | Đăng xuất rồi phát lại cookie cũ bằng client sạch | Phiên `revoked`; 303 + `/api/me` 401 | PASS |
| 3 | `test_phien_het_han_tuyet_doi` | DB đặt `expires_at` quá khứ, `last_seen_at` hiện tại | Bị đẩy về đăng nhập; `/api/me` 401; phiên `expired` | PASS |
| 4 | `test_phien_idle_timeout` | DB đặt `last_seen_at` quá `idle_minutes + 1`, `expires_at` còn xa | 303/401; phiên `expired` | PASS |
| 5 | `test_tai_khoan_bi_khoa_giua_phien` | DB đặt `users.status='suspended'` khi đang có phiên | Request sau 303; `/api/me` 401; phiên `revoked` lý do "Tài khoản…" | PASS |
| 6 | `test_cookie_httponly_samesite_lax_secure_khi_https` | Login HTTP, HTTPS thật (`base_url=https`), và `X-Forwarded-Proto: https` | HTTP: HttpOnly + SameSite=lax + Path=/, **không** Secure; HTTPS/proxy: có Secure, vẫn đăng nhập được | PASS |
| 7 | `test_csrf_thieu_sai_va_token_cua_phien_khac` | Thiếu token, token sai, token CSRF của phiên thứ hai **cùng người dùng** | Cả 3 → 403, dữ liệu không đổi; token đúng → 303 và cập nhật thật | PASS |
| 8 | `test_rate_limit_5_lan_sai_tren_10_phut_theo_user_ip` | 5 lần sai liên tiếp rồi mật khẩu đúng; user khác; cùng user IP khác; bản ghi ra ngoài cửa sổ 10 phút | Lần 6 bị "tạm khoá"; user khác và IP khác không bị chặn; ngoài cửa sổ không tính | PASS |
| 9 | `test_thong_bao_khong_lo_user_ton_tai` | So sánh flash của user tồn tại vs ID không tồn tại ở lần sai đầu và sau 5 lần sai | Chuỗi thông báo giống hệt nhau ở cả hai mốc | PASS |
| 10 | `test_thoi_gian_tra_loi_khong_lo_user_ton_tai` | Đo trung vị 5 lần POST cho user tồn tại vs không tồn tại (xen kẽ) | Cả hai > 5 ms (scrypt thật chạy); tỷ lệ trung vị trong khoảng 0,4–2,5 | PASS |
| 11 | `test_doi_mat_khau_thu_hoi_moi_phien_khac` | 2 phiên cùng user; đổi mật khẩu ở phiên A | Token cũ A và B đều `revoked`, 401; phiên mới A hoạt động; mật khẩu mới đăng nhập được, cũ không | PASS |
| 12 | `test_dat_lai_mat_khau_thu_hoi_moi_phien` | Super Admin đặt lại mật khẩu user đang có phiên | Phiên cũ `revoked` + 401; mật khẩu cũ chết; mật khẩu tạm đăng nhập được và bị đưa tới `/doi-mat-khau` | PASS |
| 13 | `test_db_chi_luu_hash_scrypt_va_khong_luu_token_tho` | Quét toàn bộ bảng/cột SQLite tìm mật khẩu và token thô | `password_algo='scrypt'`, hash 32B + salt 16B; `token_hash = sha256(token) ≠ token`; không bảng nào chứa mật khẩu/token thô | PASS |
| 14 | `test_dang_nhap_thanh_cong_xoa_bo_dem_sai` | 4 lần sai → đăng nhập đúng → đăng xuất → 1 lần sai → đăng nhập đúng | Không bị khoá oan; bộ đếm `success=0` về 0 | PASS |
| 15 | `test_gioi_han_8_phien_khong_thu_hoi_phien_vua_tao` | 8 phiên cũ mang `created_at` "mới hơn" phiên thứ 9 (mô phỏng trùng giây/lùi đồng hồ) | Phiên vừa tạo vẫn `active`, đăng nhập được; đúng 8 phiên sống | PASS |

---

## 3. Lỗi thật đã sửa (tối thiểu, trong `cowork/auth.py`)

### 3.1. Bộ đếm `login_attempts` không được xoá sau đăng nhập thành công → khoá oan

- **Hiện trạng trước sửa:** `users.failed_attempts` được đặt lại 0, nhưng rate limit lại đọc bảng
  `login_attempts`; các dòng `success=0` cũ vẫn còn. Kịch bản: 3 lần sai → đăng nhập đúng →
  đăng xuất → 2 lần sai → lần đăng nhập đúng kế tiếp bị chặn "tạm khoá 10 phút".
  Đã tái hiện thủ công trước khi sửa (bộ đếm còn 5 dòng `success=0`, lần đúng bị chặn).
- **Sửa:** ngay sau khi xác thực mật khẩu + trạng thái tài khoản thành công, xoá
  `login_attempts` của đúng cặp `(user_id, ip)` với `success=0` rồi mới ghi lần đăng nhập thành công.
- **Vì sao an toàn:** kẻ tấn công không có mật khẩu đúng thì không kích hoạt được nhánh này;
  rate limit theo IP và theo user (15 lần/30 phút xuyên IP) vẫn giữ nguyên cho các lần sai.
- **Test canh:** #14. API/chữ ký hàm không đổi. 14 test cũ vẫn xanh, gồm `test_dang_nhap_sai_va_khoa_tam`.

### 3.2. Giới hạn 8 phiên có thể thu hồi nhầm chính phiên vừa tạo

- **Hiện trạng trước sửa:** `tao_phien` chèn phiên mới rồi `SELECT … ORDER BY created_at DESC`
  và thu hồi `rows[8:]`. `created_at` chỉ có độ phân giải **giây**, nên khi 8 phiên cũ trùng giây
  (hoặc đồng hồ bị lùi), thứ tự không xác định và phiên mới có thể nằm trong `rows[8:]`
  → đăng nhập thành công nhưng cookie vừa cấp bị `revoked` ngay.
  Đã tái hiện thủ công 5/5 lần: phiên mới `revoked`, còn 8 phiên cũ `active`.
- **Sửa:** sắp xếp xác định `ORDER BY created_at DESC, rowid DESC`; loại hẳn `sid` (phiên vừa tạo)
  khỏi danh sách bị thu hồi; giữ tối đa 8 phiên sống.
- **Test canh:** #15. Không đổi API, không đổi schema, không đổi thông điệp/hành vi các test cũ.

---

## 4. Rủi ro còn lại (không sửa trong làn này)

1. **Mở khoá tài khoản không xoá bộ đếm sai (ngoài vùng):** `services.doi_trang_thai(..., 'active')`
   / route `POST /tai-khoan/{id}/mo-khoa` chỉ đổi `users.status`, không xoá `login_attempts`.
   Người bị khoá do 5 lần sai vẫn phải chờ hết cửa sổ 10/30 phút dù quản trị đã "mở khoá".
   Đề nghị controller/AG-03 bổ sung xoá `login_attempts` của user khi mở khoá.
2. **IP sau reverse proxy:** `run.sh` không đặt `--proxy-headers`/`--forwarded-allow-ips`.
   Nếu mọi request tới app đều có `request.client.host` là IP proxy, rate limit "theo user+IP"
   suy biến thành "theo user" (vẫn còn chặn 5 lần/10 phút); cần xác nhận cấu hình uvicorn/Caddy
   khi lên production. Ngoài phạm vi `auth.py` (file `run.sh` thuộc controller).
3. **`dat_cookie` dùng `config.SESSION_HOURS` cho `Max-Age`,** còn máy chủ dùng setting DB
   `security.session_hours`. Nếu quản trị đổi setting, thời hạn cookie trình duyệt và phiên máy chủ
   lệch nhau (máy chủ luôn là nguồn quyết định; không phải lỗ hổng vượt phiên, chỉ là trải nghiệm).
   Muốn sửa cần truyền `conn`/giá trị hiệu lực vào `dat_cookie` — ngoài mức "sửa tối thiểu".
4. **CSRF trước đăng nhập dùng double-submit cookie:** token khách do trình duyệt giữ, có thể bị
   đặt bởi kẻ tấn công nếu chiếm được subdomain/khả năng ghi cookie; sau đăng nhập CSRF gắn chặt
   với `sessions.csrf_token`. Rủi ro thấp, đúng thiết kế hiện tại.
5. **Phiên không ràng buộc UA/IP:** cookie bị đánh cắp có thể phát lại tới khi hết hạn/thu hồi;
   giảm thiểu bằng HttpOnly + SameSite=Lax + Secure khi HTTPS + thu hồi phiên + giới hạn 8 phiên.
6. **`X-Forwarded-Proto` được tin từ client:** chỉ ảnh hưởng việc bật `Secure` cho chính cookie
   của người gửi, không vượt xác thực; cần khi chạy sau Caddy.
7. **Test thời gian là thống kê:** ngưỡng rộng (trung vị 5 mẫu, tỷ lệ 0,4–2,5) để không flaky;
   không phải chứng minh constant-time tuyệt đối.
8. **Không có MFA** trong Identity hiện tại — ngoài phạm vi nhiệm vụ, không tự thêm.

---

## 5. Ghi chú vận hành

- Test dùng mật khẩu fixture của bộ test hiện có; báo cáo và log không chứa mật khẩu/token thật.
- DB test nằm trong thư mục tạm do `conftest.py` tạo; không đụng `data/cowork.db`.
- Các tệp ngoài vùng (templates, static, services, rbac, brain-bridge) đang được các làn khác sửa
  đồng thời; số test toàn bộ (54) phản ánh thời điểm chạy cuối, phần bắt buộc của AG-02 là 29 test
  (14 cũ + 15 mới) đã xanh. Trong lúc chạy có một lần `tests/test_e2e_ag05.py` (làn AG-05) đang được
  sửa dở và fail; sau khi AG-05 hoàn tất, chạy lại toàn bộ xanh (exit 0).
