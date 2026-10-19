# NGHIỆM THU COWORK — 8 BƯỚC DÀNH CHO CHỦ DỰ ÁN

**Người nghiệm thu:** anh-thanh (Super Admin)
**Môi trường hiện tại:** local/staging — `http://127.0.0.1:8899` + Brain staging `http://127.0.0.1:8892`
**Môi trường production (sau phê duyệt):** `https://cowork.vipgroup.com.vn` + `https://ai.vipgroup.com.vn`
**Nguyên tắc:** chỉ đánh **PASS** khi thao tác thật, AI Local trả lời thật; **không** chấp nhận MOCK.

---

## 0. CHUẨN BỊ

- [ ] COWORK đang chạy (`/api/health` trả `ok`).
- [ ] Brain staging đang chạy (`127.0.0.1:8892/api/health` trả `ok`) và bridge bật.
- [ ] Ollama tunnel `127.0.0.1:11434` hoạt động; model `qwen2.5:7b-instruct` có thật.
- [ ] Có 3 cửa sổ trình duyệt riêng (hoặc 3 profile/incognito) cho Super Admin, Quản trị, Nhân viên.
- [ ] Mật khẩu `anh-thanh` đọc từ `secrets/owner-anh-thanh.txt` (local) hoặc bàn giao bảo mật (production).
- [ ] Không dùng chung cookie giữa các cửa sổ.

---

## BƯỚC 1 — anh-thanh đăng nhập

**Làm:**
1. Mở COWORK → `/dang-nhap`.
2. Nhập ID `anh-thanh` + mật khẩu.
3. Kiểm tra dashboard hiển thị “Chào anh-thanh”, vai trò Super Admin, 15 module.

**Kỳ vọng:**
- Vào được dashboard, sidebar có nhóm Quản trị.
- `/tai-khoan`, `/ban`, `/vai-tro`, `/nhat-ky`, `/cai-dat` mở được.
- Audit có dòng `auth.login`.

**Bằng chứng:** ảnh dashboard + thời điểm đăng nhập.

---

## BƯỚC 2 — Tạo quản trị cấp dưới

**Làm:**
1. `Tài khoản` → `Tạo tài khoản`.
2. ID: `quan-tri-nghiem-thu` (hoặc ID riêng), tên, vai trò **Quản trị cấp dưới**.
3. Phạm vi: **Toàn tenant** (hoặc chọn ban để thử phạm vi hẹp).
4. Đặt mật khẩu tạm mạnh; lưu lại để đăng nhập.

**Kỳ vọng:**
- Tạo thành công; tài khoản xuất hiện trong danh sách với badge “Quản trị cấp dưới”.
- Audit có `account.create` + `account.scope`, actor `anh-thanh`.
- Form **không** cho chọn Super Admin.

**Bằng chứng:** ảnh chi tiết tài khoản + ID audit.

---

## BƯỚC 3 — Quản trị tạo nhân viên theo ban

**Làm:**
1. Đăng xuất Super Admin; đăng nhập `quan-tri-nghiem-thu` ở cửa sổ riêng.
2. `Tài khoản` → `Tạo tài khoản`.
3. ID nhân viên, vai trò **Nhân viên**, ban **Ban Kinh doanh**, mật khẩu tạm.
4. Kiểm tra quản trị **không** tạo được vai trò Quản trị/Super Admin.

**Kỳ vọng:**
- Tạo nhân viên thành công.
- Quản trị không thấy/không sửa được Super Admin `anh-thanh`.
- Nếu quản trị bị giới hạn Ban Kinh doanh: không tạo được nhân viên Ban Kỹ thuật (báo ngoài phạm vi).
- Audit actor là `quan-tri-nghiem-thu`, target là nhân viên.

**Bằng chứng:** ảnh form + ảnh lỗi ngoài phạm vi (nếu thử) + audit.

---

## BƯỚC 4 — Nhân viên đăng nhập

**Làm:**
1. Đăng xuất quản trị; mở cửa sổ riêng, đăng nhập bằng ID nhân viên + mật khẩu tạm.
2. Nếu hệ thống yêu cầu đổi mật khẩu lần đầu, đổi sang mật khẩu riêng rồi đăng nhập lại.

**Kỳ vọng:**
- Vào được dashboard nhân viên.
- Không thấy nhóm Quản trị trên sidebar.
- Audit `auth.login` đúng ID nhân viên.

**Bằng chứng:** ảnh dashboard nhân viên.

---

## BƯỚC 5 — Nhân viên chỉ thấy module được cấp

**Làm:**
1. Đối chiếu sidebar với `/api/me` (mở trực tiếp).
2. Thử mở thẳng `/tai-khoan`, `/ban`, `/vai-tro`, `/nhat-ky`, `/cai-dat`.

**Kỳ vọng:**
- Sidebar chỉ có module được cấp (mặc định nhân viên: Bảng điều khiển, VIP AI Brain, Công việc, Tri thức, Sử dụng & chi phí).
- Các URL quản trị trả **403 Không đủ quyền**, không lộ dữ liệu.
- `/api/me` trả đúng danh sách module và quyền.

**Bằng chứng:** ảnh sidebar + ảnh 403 + JSON `/api/me` (đã lọc).

---

## BƯỚC 6 — Mở VIP AI Brain từ COWORK

**Làm:**
1. Nhân viên vào module **VIP AI Brain** → bấm **Mở VIP AI Brain**.
2. Quan sát: trình duyệt chuyển sang Brain (`/cowork/vao?ticket=...`) rồi vào giao diện Brain.
3. **Không** nhập lại mật khẩu, **không** hỏi MFA của Brain.

**Kỳ vọng:**
- Vào được Brain với đúng danh tính nhân viên (`/api/auth/toi` trả đúng ID).
- Không có form đăng nhập/MFA thứ hai.
- Audit COWORK có `brain.launch`; audit Brain có `COWORK: Mở phiên`.
- `anh-thanh` (đang bật MFA) **không** mở được qua COWORK trong giai đoạn này — đây là chốt an toàn có chủ ý, không phải lỗi.

**Bằng chứng:** ảnh Brain sau khi mở + `/api/auth/toi` + audit hai phía.

---

## BƯỚC 7 — AI Local trên Mac Studio trả lời thật

**Làm:**
1. Trong Brain, hỏi:
   > “Xin chào VIP AI Brain. Hãy xác nhận mô hình AI Local đang xử lý yêu cầu này và cho tôi biết những chức năng hiện có thể sử dụng.”
2. Chờ trả lời; kiểm tra metadata backend (provider/model).

**Kỳ vọng:**
- Câu trả lời có nội dung thật, đúng tiếng Việt, không phải mock.
- Metadata: `providerId=local`, `nhan=real`, model `qwen2.5:7b-instruct`; không gọi cloud.
- Không có dấu hiệu “MOCK” trong response.

**Bằng chứng:** ảnh câu trả lời + JSON response (đã lọc) + log Ollama/Brain.

**Nếu chỉ thấy MOCK/cloud → đánh FAIL, không PASS.**

---

## BƯỚC 8 — Thu hồi quyền và xác minh bị chặn

**Làm:**
1. Super Admin mở `Tài khoản` → nhân viên → `Phân quyền`.
2. Chặn module **VIP AI Brain** (chọn “Chặn”) → Lưu.
3. Ở cửa sổ nhân viên: tải lại trang, thử mở lại Brain.
4. Thử thu hồi toàn bộ phiên của nhân viên.

**Kỳ vọng:**
- Module VIP AI Brain biến mất khỏi sidebar nhân viên ngay.
- `/brain` trả 403; nút mở Brain không còn.
- Phiên Brain cũ bị thu hồi (`/api/auth/toi` → 401) — không dùng tiếp được.
- Thu hồi phiên COWORK → request sau chuyển về `/dang-nhap`.
- Audit ghi `permissions.update`, `account.revoke_sessions`; actor `anh-thanh`.
- Cấp lại quyền (Theo vai trò) → nhân viên mở lại được sau khi đăng nhập/launch lại.

**Bằng chứng:** ảnh trước/sau + HTTP 403/401 + audit.

---

## BẢNG KÝ NGHIỆM THU

| Bước | Nội dung | Kết quả (PASS/FAIL) | Bằng chứng | Ghi chú |
|---|---|---|---|---|
| 1 | anh-thanh đăng nhập | ⬜ | | |
| 2 | Tạo quản trị cấp dưới | ⬜ | | |
| 3 | Quản trị tạo nhân viên | ⬜ | | |
| 4 | Nhân viên đăng nhập | ⬜ | | |
| 5 | Chỉ thấy module được cấp | ⬜ | | |
| 6 | Mở Brain, không đăng nhập lần hai | ⬜ | | |
| 7 | AI Local trả lời thật | ⬜ | | |
| 8 | Thu hồi quyền bị chặn | ⬜ | | |

**Kết luận:** ⬜ PASS toàn bộ · ⬜ PASS có điều kiện · ⬜ FAIL
**Chữ ký chủ dự án:** ____________________  **Ngày:** ____________
**Controller:** __________________________

---

## ĐIỀU KIỆN KHÔNG ĐƯỢC PASS

- Bất kỳ bước nào chỉ dùng dữ liệu MOCK/seed mà không thao tác thật.
- Bước 7 trả lời từ cloud hoặc không có metadata local.
- Bước 8 vẫn mở được Brain sau khi thu hồi.
- Có lỗi 500 hoặc lộ dữ liệu tenant khác.

## SAU NGHIỆM THU

- Chỉ khi PASS và chủ dự án đồng ý mới xem xét:
  - thêm site block Caddy `cowork.vipgroup.com.vn`;
  - áp bridge lên Brain production;
  - cho phép tài khoản MFA mở qua COWORK / tắt MFA Brain.
- Mọi thay đổi theo `docs/TRIEN-KHAI-PRODUCTION.md` và `docs/ROLLBACK.md`.
