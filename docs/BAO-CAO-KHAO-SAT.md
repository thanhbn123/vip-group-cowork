# BÁO CÁO KHẢO SÁT — VIP GROUP COWORK

**Ngày khảo sát:** 19/10/2026
**Người thực hiện:** Master Project Controller (DeepSeek Harness)
**Phạm vi:** máy MacBook của chủ dự án, Mac Studio (VIP AI Brain), VPS `160.22.170.20`, DNS `vipgroup.com.vn`
**Nguyên tắc:** chỉ đọc — không sửa, không deploy, không push, không đụng dữ liệu thật.

**Tên miền chính thức (chốt 19/10/2026):** COWORK = `https://cowork.vipgroup.com.vn` · VIP AI Brain = `https://ai.vipgroup.com.vn`. Chi tiết kiểm tra: `docs/CAU-HINH-TEN-MIEN.md`.

---

## 1. KẾT LUẬN NHANH

| Câu hỏi | Kết luận |
|---|---|
| Đã có dự án COWORK chưa? | **CHƯA CÓ.** Không có source code, giao diện, backend hay database COWORK. |
| Có tên miền dành cho COWORK chưa? | **DNS đã đúng, chưa có site block.** `cowork.vipgroup.com.vn` trỏ `160.22.170.20`; Caddy chưa cấu hình tên này nên HTTPS lỗi `TLS alert internal error`. Không cần đổi DNS. |
| Có gì đang chạy thật? | **VIP AI Brain** production tại `https://ai.vipgroup.com.vn`: FastAPI + SQLite `vip-brain.db`, AI Local `qwen2.5:7b-instruct` trên Mac Studio, 1 tenant, 7 user. |
| Có được xây lại Brain không? | **KHÔNG.** Brain giữ nguyên; COWORK là lớp ứng dụng mới, gọi Brain như dịch vụ AI. |
| Phần nào tái dùng được? | ID người dùng, phiên đăng nhập, tenant, audit, mô hình quyền theo dự án, Ollama/AI Local, tunnel VPS, backup — của Brain. |
| Phần lớn nhất còn thiếu? | **Toàn bộ COWORK**: ID lifecycle, RBAC 5 vai trò, ban/bộ phận, module registry, phân quyền module, nhật ký quản trị, SSO COWORK → Brain. |

> **Tóm một câu:** chưa có COWORK để "hoàn thiện"; có một VIP AI Brain đang chạy thật với nền xác thực/tenant/audit đủ tốt để COWORK **kế thừa và bọc lên trên**, không xây lại.

---

## 2. BẰNG CHỨNG KHẢO SÁT

### 2.1. Tìm dấu vết COWORK trên toàn hệ

| Lệnh / cách kiểm | Kết quả |
|---|---|
| `find ~ -maxdepth 5 -iname "*cowork*"` | Chỉ có log của ứng dụng Claude và ảnh kiến trúc `~/Downloads/Kiến trúc hệ thống VIP Group Cowork và AI Brain.png`. **Không có thư mục dự án.** |
| `rg -l -i "cowork" ~/code ~/Projects` | **0 tệp** trong toàn bộ các repo đang có. |
| `rg -l -i "cowork" ~/.claude/projects ~/.codex` | **0 phiên** lập trình trước đó. |
| `find ~/Library/CloudStorage -maxdepth 3 -iname "*cowork*"` | **0 kết quả** trên hai ổ Synology Drive. |
| `dig +short cowork.vipgroup.com.vn` | `160.22.170.20` (DNS đã chuẩn bị). |
| `curl -I https://cowork.vipgroup.com.vn/` | `000` / `tlsv1 alert internal error` — **chưa có site block + chứng chỉ**. |
| `dig +short @8.8.8.8 cowork.vipgroup.com.vn` | `160.22.170.20` — DNS đã lan truyền. |
| Caddy VPS | `v2.11.4`, container `vip-staging-caddy`, **không có block `cowork`**; cổng `18835` đang trống. |
| `dig +short id.vipgroup.com.vn` | `160.22.170.20` — tên phụ, chưa có dịch vụ; không dùng làm tên chính thức. |

**Kết luận:** COWORK là dự án **greenfield**, không phải dự án đang dở cần sửa. Việc "không xây lại phần đã có" áp dụng cho **VIP AI Brain**, không áp dụng cho COWORK.

### 2.2. VIP AI Brain — hiện trạng production

| Hạng mục | Giá trị đo được | Bằng chứng |
|---|---|---|
| URL công khai | `https://ai.vipgroup.com.vn` → HTTP 200 | `curl -I` |
| Hạ tầng | VPS `160.22.170.20` (Caddy) → SSH reverse tunnel `127.0.0.1:18834` → Mac Studio `127.0.0.1:8891` | `com.vipai.brain.tunnel-vps.plist`, `tunnel-vps.sh` |
| Backend | FastAPI, Python 3.12.15, chạy bằng launchd `com.vipai.brain.backend` | plist + `run-backend.sh` |
| Database | `/Users/macstudio/VIP-AI/brain/data/vip-brain.db` (SQLite), integrity `ok` | `/api/health`; `sqlite3` |
| Tenant | **1**: `vip-group` — "VIP Group" | `SELECT * FROM tenants` |
| Người dùng | **7**: 1 chủ sở hữu đang hoạt động (`anh-thanh`), 1 kế toán chưa kích hoạt, 5 tài khoản test đã khoá | `SELECT id, vaiTro, trangThai FROM users` |
| Vai trò hiện có | `chu-so-huu`, `quan-tri`, `thanh-vien` (3 vai trò thô) | `app/store/boi_canh.py` |
| Đăng nhập | ID + mật khẩu (scrypt), rate-limit 5 lần sai/10 phút theo user+IP, thông báo lỗi chung | `app/api/auth.py` |
| MFA | TOTP cho `anh-thanh`, mã dự phòng; **đang bật** | `mfa_repo`, `MFA_BAT`, tài liệu FINAL_SECURITY_STATUS |
| Phiên | Cookie `vip_session` HttpOnly/SameSite=Lax, token lưu SHA-256, hạn 24h + idle 120 phút, thu hồi được | `sessions_repo.py` |
| Audit | **185 dòng**, ghi login/MFA/chat/từ chối quyền | `SELECT COUNT(*) FROM audit` |
| Phân quyền dữ liệu | `project_permissions` (2 dòng), `tool_permissions`, `agent_permissions`; lọc tenant ở tầng repo | `boi_canh.where_quyen` |
| AI Local | Ollama trên Mac Studio, model `qwen2.5:7b-instruct`, 100% GPU; policy `NO_CLOUD=1`, `VIP_AI_LOCAL_ONLY=1` | FINAL_LOCAL_AI_STATUS + kiểm tra trực tiếp |
| Code Execution | **OFF** | `.env`, tài liệu FINAL_SECURITY_STATUS |
| Backup | Hằng ngày trên Studio + MacBook, mã hoá AES-256 đẩy Synology; đã test decrypt/restore | `FINAL_BACKUP_RECOVERY.md`, `status-live.json` |
| Git | nhánh `main`, commit `37c9c39`, **ahead 18**, chưa push | `git log`, `git status` |

### 2.3. Giao diện Brain hiện tại

- Frontend tĩnh `frontend/brain/index.html` + `app.js` (166 KB) + `ds-api.js` (83 KB).
- Tiêu đề trang: **"VIP AI BRAIN — DEMO"**; có badge `MOCK`/`BACKEND`, tự dò `/api/health` và chuyển sang backend thật.
- Có overlay đăng nhập thật (`/api/auth/dang-nhap`, bước MFA) khi backend trả `401 CHUA_DANG_NHAP`.
- Đây là **giao diện demo/prototype đã nối được backend**, chưa phải giao diện COWORK và chưa được chủ dự án nghiệm thu bằng mắt (theo `FINAL_PRODUCTION_HANDOVER.md`).

### 2.4. Các khoảng trống đã được ghi nhận trong hồ sơ Brain

| Khoảng trống | Nguồn |
|---|---|
| "Module tài khoản/phân quyền mới và bỏ MFA chưa triển khai (đang giữ MFA)" | `FINAL_SECURITY_STATUS.md` |
| `GET /api/settings` chưa giới hạn `quan-tri+` trên production — **authorization GAP** | `FINAL_SECURITY_STATUS.md` |
| HSTS/XFO/CSP mới có ở runtime, chưa persist vào Caddyfile (mất khi restart Caddy) | `FINAL_PRODUCTION_HANDOVER.md` |
| Dữ liệu test còn trong DB live; chờ phê duyệt manifest xoá | `FINAL_DATA_CLEANUP_MANIFEST.md` |
| Frontend chưa được kiểm thủ công toàn bộ; chưa kết luận UI PASS | `FINAL_PRODUCTION_HANDOVER.md` |
| Không có API/UI tạo tài khoản: chỉ có CLI `python -m app.store.tao_tai_khoan` trên Mac Studio | `app/store/tao_tai_khoan.py` |

---

## 3. ĐỐI CHIẾU VỚI KIẾN TRÚC CHỦ DỰ ÁN

Ký hiệu: ✅ có và dùng được · 🟡 có một phần · ❌ chưa có

| # | Yêu cầu kiến trúc | Brain hiện có | COWORK hiện có | Việc cần làm |
|---|---|---|---|---|
| 1 | `anh-thanh` là Super Admin cao nhất | 🟡 `chu-so-huu` trong Brain, không có khái niệm Super Admin COWORK | ❌ | Tạo vai trò `super_admin` bất biến, bảo vệ không ai sửa/xoá |
| 2 | Super Admin tạo quản trị cấp dưới | ❌ chỉ CLI, không phân cấp | ❌ | API + màn tạo tài khoản, chặn leo thang |
| 3 | Tạo trưởng ban / nhân viên | ❌ | ❌ | 5 vai trò + phạm vi ban |
| 4 | Tạo ban/bộ phận | ❌ | ❌ | Bảng `departments`, gán trưởng ban, scope |
| 5 | Cấp/thu hồi quyền | 🟡 project/tool/agent permissions, không có UI | ❌ | Role-permission + user override + thu hồi tức thời |
| 6 | Quản lý module | ❌ không có module registry | ❌ | Bảng `modules`, bật/tắt, thứ tự, quyền tối thiểu |
| 7 | Xem nhật ký hệ thống | 🟡 có bảng `audit` + API, không có UI | ❌ | Màn nhật ký, lọc, xuất CSV, append-only |
| 8 | Quản trị cấp dưới chỉ trong phạm vi | ❌ | ❌ | Scope tenant/ban + luật "không vượt cấp" |
| 9 | Không tự nâng quyền, không sửa Super Admin | ❌ | ❌ | Kiểm tra ở service + test đối kháng |
| 10 | Nhân viên đăng nhập bằng ID, chỉ thấy module được cấp | 🟡 ID + phiên, không có module | ❌ | Sidebar/menu tính từ quyền hiệu lực mỗi request |
| 11 | Tenant isolation | ✅ lọc tenant ở repo | ❌ | Lọc tenant ở mọi truy vấn COWORK + test |
| 12 | Audit log | 🟡 có bảng, chưa UI | ❌ | Audit append-only cho mọi hành động quản trị |
| 13 | Session revocation | ✅ trong Brain | ❌ | Phiên COWORK + thu hồi + đẩy thu hồi sang Brain |
| 14 | Partner | ❌ | ❌ | Vai trò `partner`, cổng đối tác, chỉ module được cấp |
| 15 | SSO COWORK → Brain, không đăng nhập lần hai | ❌ | ❌ | Ticket one-time + HMAC + phiên Brain native |
| 16 | Kiểm tra quyền tại backend Brain | 🟡 quyền dự án, không quyền module COWORK | ❌ | Bridge từ chối ticket nếu COWORK không cấp module Brain |
| 17 | Không tắt bảo vệ cũ sớm | ✅ MFA đang bật | — | Giữ MFA; bridge có cờ riêng, mặc định không bỏ qua MFA cho tài khoản MFA |
| 18 | Không đụng `vip-brain.db` | ✅ | — | COWORK dùng DB riêng `cowork.db`; bridge chỉ ghi phiên/user shadow khi được bật |

---

## 4. PHẦN ĐÃ HOÀN THIỆN (TÁI DÙNG, KHÔNG XÂY LẠI)

1. **ID + mật khẩu + phiên** của Brain: scrypt, cookie HttpOnly, rate limit, thu hồi phiên, audit.
2. **Tenant `vip-group`** và cách lọc tenant tập trung ở `boi_canh.where_quyen`.
3. **Mô hình quyền theo dự án/công cụ/agent** — dùng làm tham chiếu, không thay thế.
4. **Audit 185 dòng** với các sự kiện đăng nhập/MFA/chat/từ chối.
5. **AI Local thật** trên Mac Studio (`qwen2.5:7b-instruct`), policy local-only, code execution OFF.
6. **Đường hầm VPS → Mac Studio** và backup mã hoá đã được nghiệm thu kỹ thuật.
7. **Giao diện demo** có login overlay và lớp API — dùng làm nơi đến sau khi SSO, không dùng làm COWORK.

---

## 5. PHẦN CẦN BỔ SUNG (PHẠM VI COWORK)

### 5.1. Lõi ID & phân quyền
- 5 vai trò: `super_admin`, `admin` (quản trị ủy quyền), `department_manager`, `employee`, `partner`.
- Ban/bộ phận có trưởng ban, thành viên, phạm vi quản trị.
- Quyền theo module + hành động; quyền riêng của user (allow/deny) chồng lên quyền vai trò.
- Luật chống leo thang: không tạo/sửa vai trò ngang hoặc cao hơn; không cấp quyền mình không có; không chạm Super Admin; không tự đổi vai trò mình.
- Tenant isolation ở mọi truy vấn; ID toàn cục duy nhất trong tenant.
- Phiên máy chủ, CSRF, rate limit, đổi mật khẩu, thu hồi phiên đơn lẻ/toàn bộ.
- Audit append-only (trigger chặn UPDATE/DELETE), có lọc và xuất CSV.

### 5.2. Màn hình COWORK
- Dashboard theo vai trò.
- Quản lý tài khoản: danh sách, tạo, sửa, khoá/mở, đặt lại mật khẩu, thu hồi phiên, lưu trữ.
- Quản lý ban/bộ phận: tạo/sửa, gán trưởng ban, đếm thành viên.
- Quản lý vai trò: ma trận quyền theo module/hành động.
- Phân quyền module cho từng user: theo vai trò / chỉ xem / sử dụng / chặn.
- Nhật ký quản trị: ai làm gì, lúc nào, từ IP nào, kết quả.
- Module registry: bật/tắt, thứ tự, quyền tối thiểu, đánh dấu module cần Brain.
- Cài đặt: tenant, chính sách phiên, kết nối Brain, kiểm tra sức khoẻ.
- Cổng đối tác: chỉ module được cấp.

### 5.3. Cầu nối VIP AI Brain
- COWORK phát **ticket one-time** (60 giây) khi user có quyền module Brain.
- Brain staging xác thực ticket qua HMAC, tạo **phiên Brain native** cho đúng user, không hỏi mật khẩu/MFA lần hai.
- Thu hồi quyền/khoá user → COWORK gọi Brain thu hồi phiên ngay.
- Mặc định **không** bỏ qua MFA cho tài khoản đang bật MFA (`anh-thanh`) cho tới khi chủ dự án nghiệm thu COWORK.
- Bản vá Brain nằm ngoài production, có script áp dụng/rollback; production chỉ nhận sau phê duyệt.

---

## 6. RỦI RO & RÀNG BUỘC

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Sửa Brain production làm gián đoạn dịch vụ | Cao | Không sửa production trong giai đoạn này; chỉ chạy **Brain staging** trên bản sao DB, cổng riêng |
| Xung đột cookie/phiên giữa COWORK và Brain | Trung bình | Tên cookie khác nhau; bridge tạo phiên Brain native; test trên staging |
| Leo thang quyền qua API | Cao | Kiểm tra ở service + test đối kháng; không tin dữ liệu form |
| Lộ mật khẩu/ticket trong log | Cao | Không log mật khẩu/token/ticket; chỉ log hash/ID; file secret 0600 |
| Dữ liệu thật bị xoá | Cao | Không xoá cứng; lưu trữ mềm; backup trước mỗi lần migrate; audit append-only |
| COWORK chết làm mất đường vào Brain | Trung bình | Brain vẫn đăng nhập trực tiếp bằng MFA như cũ; bridge là kênh phụ |
| Deploy nhầm | Cao | Không deploy; chỉ chạy local/staging, bàn giao script và phê duyệt |

---

## 7. KẾ HOẠCH TRIỂN KHAI

| Bước | Nội dung | Điều kiện hoàn thành | Trạng thái |
|---|---|---|---|
| P1 | Khảo sát (báo cáo này) | Có bằng chứng, không sửa gì | ✅ xong |
| P2 | Lõi COWORK: DB, auth, RBAC, tenant, audit, session | Test bảo mật xanh; seed 5 vai trò | ✅ xong (14 test + agent bổ sung) |
| P3 | Màn hình COWORK | 8 màn hình dùng được, responsive | ✅ xong (15+ màn hình, có ảnh) |
| P4 | Cầu nối Brain staging | Ticket one-time, phiên Brain, chat local thật, thu hồi chặn | 🔄 đang nghiệm thu (ticket + phiên Brain đã chạy; chat local đang vá quyền dự án chung) |
| P5 | Nghiệm thu 8 bước | Có log + ảnh/JSON, không MOCK | 🔄 5 agent đang chạy; controller tích hợp |
| P6 | Bàn giao | Tài liệu chạy, tài khoản, rollback, kế hoạch production | 🔄 tài liệu đã soạn; chờ bằng chứng cuối |

### 7.1. Điều kiện "đủ điều kiện để làm ngay"
- Chỉ ghi trong workspace `VIP GROUP ID/cowork`.
- Không sửa `vip-brain.db` production.
- Không restart Brain production.
- Không deploy VPS, không push GitHub.
- Brain staging dùng **bản sao DB** và **cổng riêng** trên MacBook; Ollama gọi qua tunnel SSH tới Mac Studio.

### 7.2. Điều kiện cần chủ dự án phê duyệt (chưa làm)
- Áp dụng bản vá bridge lên Brain production.
- Đổi Caddy/route `cowork.vipgroup.com.vn`.
- Bỏ MFA Brain sau nghiệm thu COWORK.
- Xoá dữ liệu test trong `vip-brain.db`.

---

## 8. QUYẾT ĐỊNH KIẾN TRÚC ĐỀ XUẤT

1. **COWORK là ứng dụng riêng**, DB riêng `cowork.db`, không nhét bảng quản trị vào `vip-brain.db`.
2. **COWORK là nguồn danh tính** cho nhân sự; Brain là **nhà cung cấp AI** và vẫn giữ đăng nhập trực tiếp dự phòng.
3. **SSO bằng ticket one-time + HMAC**, không chia sẻ mật khẩu, không lưu mật khẩu Brain.
4. **Brain tạo phiên native** cho user COWORK → mọi route Brain hiện có dùng lại nguyên vẹn, audit vẫn ghi đúng người.
5. **Quyền module kiểm tại COWORK**, và **Brain từ chối cấp phiên** nếu ticket không có quyền module Brain → kiểm quyền ở cả hai đầu.
6. **MFA Brain giữ nguyên**; bridge có cờ `COWORK_BRIDGE_ALLOW_MFA_USERS`, mặc định `0` cho tới khi nghiệm thu.
7. **Không đụng dữ liệu thật**: mọi thử nghiệm trên bản sao; bản sao có nhãn `STAGING` trong tên DB.

---

## 9. VIỆC LÀM TIẾP THEO

1. Dựng COWORK trong `cowork/` (P2, P3).
2. Dựng Brain staging + bridge (P4).
3. Chạy bộ nghiệm thu 8 bước, lưu bằng chứng (P5).
4. Bàn giao tài liệu, tài khoản, rollback (P6).

**Không có thay đổi nào trên production trong toàn bộ giai đoạn này.**
