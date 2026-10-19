# AG-04 — BÁO CÁO BRAIN STAGING & E2E SSO COWORK → VIP AI BRAIN

**Ngày:** 19/10/2026 · **Làn:** AG-04 VIP AI BRAIN INTEGRATION
**Trạng thái:** ✅ PASS — Brain staging sống ở `127.0.0.1:8892`; E2E thật (không mock) a–f đạt.
**Môi trường:** MacBook · COWORK `127.0.0.1:8899` · Brain staging `127.0.0.1:8892` · Ollama tunnel `127.0.0.1:11434` · model `qwen2.5:7b-instruct`.
**Không chạm:** Brain production `127.0.0.1:8891`, `vip-brain.db` production, Caddy/DNS/VPS; không deploy/push/commit.

---

## 0. KẾT LUẬN NGẮN

1. Đã sửa đúng lỗi quote trong `scripts/provision_brain_staging.sh` và `brain-staging/.env`; `source .env` không còn lỗi `GROUP: command not found`.
2. Brain staging đã khởi động, `/api/health` 200, `/api/cowork/suc-khoe` bật, dùng **bản sao DB staging** tại `brain-staging/data/vip-brain-staging.db`, không dùng DB production.
3. E2E thật với `nhan-vien-01` và user first-time `nhan-vien-ctrl-01`: login COWORK → ticket one-time → phiên Brain native → `POST /api/chat` thật bằng Ollama local:
   - `ok=true`, `providerId=local`, `nhan=real`, `meta.model=qwen2.5:7b-instruct`, `traLoi` không rỗng.
4. Thu hồi quyền Brain qua COWORK có hiệu lực ngay: COWORK `/brain` 403, phiên Brain cũ `GET /api/auth/toi` 401; trả quyền default xong `/brain` 200 và relaunch được.
5. Chốt MFA đúng: `anh-thanh` bị Brain trả **403 "Chưa bỏ MFA cho tài khoản này"**; `COWORK_BRIDGE_ALLOW_MFA_USERS=0` giữ nguyên.
6. Đã vá thêm hai lỗi tích hợp phát sinh trong quá trình E2E (đều trong vùng AG-04):
   - Shadow user COWORK thiếu `project_permissions` cho `tong-hop` → chat 403. Đã tự cấp **`tong-hop/doc`** khi tạo shadow, và backfill có điều kiện cho shadow cũ.
   - Ánh xạ vai trò Brain quá rộng: COWORK `admin`/`department_manager` từng thành Brain `quan-tri`. Đã hạ về `thanh-vien` (fail-closed); chỉ `super_admin` mới lên quản trị Brain, `anh-thanh` giữ `chu-so-huu`.
7. `pytest -q`: **81 test — 80 PASSED, 0 FAILED, 1 XPASS** (XPASS thuộc `tests/test_ui_ag01.py`, ngoài vùng AG-04; không làm đỏ suite). `tests/test_brain_ag04.py` có **14 test**, tất cả PASSED. Không dùng mock/cloud để kết luận PASS.

---

## 1. LỖI ĐÃ SỬA

### 1.1. Quote đường dẫn có dấu cách trong `.env` (lỗi khởi động)

**Nguyên nhân:** `scripts/provision_brain_staging.sh` sinh `.env` bằng heredoc không quote:

```sh
VIP_BRAIN_DB=$STG/data/vip-brain-staging.db
MFA_SECRET_FILE=$HOME/VIP-AI/brain/mfa_secret.txt
PYTHONPYCACHEPREFIX=$STG/pycache
```

`start-brain-staging.sh` dùng `. "$STG/.env"` (shell `source`), nên dòng chứa `VIP GROUP ID` bị tách thành lệnh `GROUP` → `GROUP: command not found`, script dừng trước khi chạy uvicorn.

**Đã sửa:** quote cả ba biến trong provision script và trong `.env` hiện có:

```sh
VIP_BRAIN_DB="$STG/data/vip-brain-staging.db"
MFA_SECRET_FILE="$HOME/VIP-AI/brain/mfa_secret.txt"
PYTHONPYCACHEPREFIX="$STG/pycache"
```

Đã kiểm tra `source` sạch (xem `evidence/AG04-checks.txt` mục 2: `SOURCE_OK`; các biến giữ nguyên dấu cách). Đồng thời sửa câu hướng dẫn cuối script từ `run-brain-staging.sh` (không tồn tại) thành `start-brain-staging.sh`.

### 1.2. Staging khởi động nhưng DB dễ bị nhầm / tạo DB rác

- Lần chạy đầu, `apply_bridge.py` kiểm tra import trong `backend/` mà không có `VIP_BRAIN_DB`, nên Brain rơi về mặc định và tạo `brain-staging/backend/vip-brain.db` (DB rỗng, không phải DB staging).
- Đã xoá DB rác này; xác minh tiến trình đang chạy chỉ ghi vào `brain-staging/data/vip-brain-staging.db` (tasks/permissions/sessions chỉ có ở DB này).
- Đã sửa `scripts/apply_bridge.py`: bước import-check dùng DB tạm `brain-staging/data/.import-check.db` + `VIP_BRAIN_BO_QUA_ENV=1`, xoá DB tạm sau khi kiểm tra. Không còn tạo `backend/vip-brain.db`, không đụng DB staging đang chạy.

### 1.3. Cấu hình staging sinh ra chế độ MOCK, không thể nghiệm thu thật

- `.env` provision ban đầu đặt `CHO_PHEP_GOI_THAT=0`; `providerConfig` của bản sao DB để `modelId` local rỗng.
- Lần chat thử đầu tiên trả `nhan=mock`, `model="<ollama-model-id>"` — đúng như thiết kế Brain khi chưa bật gọi thật. **Không dùng kết quả này để báo PASS.**
- Đã sửa **chỉ trên staging**:
  - `CHO_PHEP_GOI_THAT=1` (và trong provision script).
  - `providerConfig` local: `modelId="qwen2.5:7b-instruct"`, `bat=true`, `timeoutS=180`.
  - Giữ `VIP_AI_LOCAL_ONLY=1` (chốt fail-closed trong `app/providers/ly_do_chan_provider`), `NO_CLOUD=1` chỉ là dấu cấu hình (xem rủi ro §8).
- Sau khi sửa: mọi chat nghiệm thu đều `providerId=local`, `nhan=real`, model `qwen2.5:7b-instruct`.

### 1.4. Chat 403 vì shadow user thiếu quyền dự án chung

**Triệu chứng:** SSO thành công (`/cowork/vao` 303, `/api/auth/toi` 200) nhưng `POST /api/chat` trả 403 `KHONG_QUYEN: '...' không có quyền trên dự án 'tong-hop'`.

**Nguyên nhân:** bridge tạo shadow user vai `thanh-vien` nhưng không có dòng `project_permissions`; `api/chat.py` chặn vai `thanh-vien` nếu `boi_canh.thay_duoc(bc, "tong-hop")` false.

**Đã vá trong `brain-bridge/cowork_bridge.py`:**
- `_dam_bao_quyen_chat_chung()` cấp **đúng một quyền `doc` trên đúng dự án chung `tong-hop`** cho shadow user vai `thanh-vien`; `INSERT OR IGNORE`, không ghi đè quyền đã có.
- Không cấp dự án khác (kế toán, hải quan, logistics…), không cấp quyền ghi.
- Khi **tạo shadow mới**: cấp ngay.
- Khi **user đã tồn tại**: chỉ backfill nếu hội đủ dấu hiệu shadow cũ — **không có mật khẩu Brain** và **chưa có bất kỳ dòng `project_permissions` nào**. Tài khoản native có mật khẩu, hoặc đã có quyền dự án, không bị chạm.
- Có test riêng cho tạo mới, backfill, không đụng native có mật khẩu, không đụng tài khoản đã có quyền dự án khác.

### 1.5. Ánh xạ vai trò Brain quá rộng (fail-closed)

Theo yêu cầu bảo mật của controller, `_vai_tro_brain()` đã đổi:

| Vai trò COWORK | Vai trò Brain (trước) | Vai trò Brain (nay) |
|---|---|---|
| `super_admin` + `anh-thanh` | `chu-so-huu` | `chu-so-huu` |
| `super_admin` khác | `quan-tri` | `quan-tri` |
| `admin` | `quan-tri` | **`thanh-vien`** |
| `department_manager` | `quan-tri` | **`thanh-vien`** |
| `employee`, `partner`, vai khác | `thanh-vien` | `thanh-vien` |

Lý do: Brain `quan-tri` mở settings/audit/providers, rộng hơn phạm vi COWORK `admin`/`manager` (vốn bị giới hạn theo ban/tenant). Nếu sau này cần uỷ quyền Brain admin cho COWORK admin, phải làm cấu hình riêng có kiểm soát — không nới hàm này.

---

## 2. TRẠNG THÁI STAGING

| Hạng mục | Kết quả |
|---|---|
| Tiến trình | Brain staging PID `76205`, nghe `127.0.0.1:8892` |
| `/api/health` | **200** `{ok:true, data:{phienBan:"g02", db:"ok", ...}}` |
| `/api/cowork/suc-khoe` | **200** `{bridge:"bat", choMfa:false, coBiMat:true}` |
| DB đang dùng | `brain-staging/data/vip-brain-staging.db` — bản sao staging, 76 bảng, `PRAGMA integrity_check=ok` |
| DB production | Không mở/đọc trong đợt này; không có thao tác nào lên `127.0.0.1:8891` hay `vip-brain.db` production |
| DB rác | `brain-staging/backend/vip-brain.db`: **không còn**; `data/.import-check.db`: không còn |
| Model local | `qwen2.5:7b-instruct` (`providerConfig.local.modelId`), `bat=true`, `timeoutS=180` |
| Cờ gọi thật | `CHO_PHEP_GOI_THAT=1` · `VIP_AI_LOCAL_ONLY=1` · `NO_CLOUD=1` |
| Bridge | `COWORK_BRIDGE_BAT=1` · `COWORK_BRIDGE_ALLOW_MFA_USERS=0` · `COWORK_INTERNAL_URL=http://127.0.0.1:8899` |
| Bridge source ↔ staging copy | SHA-256 khớp: `0c25b8aceac76c1118ce0f9cc9fbca829d309e174b78e618b83ecea4843be301` |
| COWORK | `127.0.0.1:8899` vẫn là server cũ, **không restart**, không dùng cổng 8901. `/api/health` 200, `brain:"bat"` |
| Ollama | tunnel `127.0.0.1:11434` sống; model `qwen2.5:7b-instruct` có trong `/api/tags` |

> Ghi chú: hash/size DB thay đổi sau mỗi lượt test (task/audit/session). `AG04-e2e.json` là ảnh chụp tại thời điểm chạy; `AG04-checks.txt` là kiểm tra sau cùng.

---

## 3. KẾT QUẢ E2E THẬT (a–f)

Dữ liệu đầy đủ (không có mật khẩu/ticket/cookie): `evidence/AG04-e2e.json`, `evidence/AG04-backfill.json`, `evidence/AG04-revoke-nv01.json`.

### a. Đăng nhập COWORK bằng `nhan-vien-01`

- `GET /dang-nhap` 200, lấy CSRF từ form.
- `POST /dang-nhap` (`userId=nhan-vien-01`, mật khẩu đọc theo tài khoản test, `_csrf`) → **303** về `/`.
- Cookie `cowork_session` + `cowork_csrf`; `/api/me` trả tenant `vip-group`, vai `employee`, có quyền `brain.view`/`brain.use`.
- `GET /brain` → **200**.

### b. Mở `/brain` bằng POST kèm CSRF, theo redirect ticket

- Lấy `_csrf` từ trang `/brain`.
- `POST /brain/mo` → **303**.
- `Location` bắt đầu bằng `http://127.0.0.1:8892/cowork/vao?ticket=...`; **ticket không được ghi vào log/báo cáo** (chỉ kiểm tra tiền tố, độ dài).
- `GET` theo Location → Brain bridge trả **303** về `/`; cookie `vip_session` được set (HttpOnly).

### c. Brain tạo phiên native — không hỏi mật khẩu/MFA lần hai

`GET http://127.0.0.1:8892/api/auth/toi` → **200**:

```json
{
  "userId": "nhan-vien-01",
  "ten": "Nguyễn Văn Nhân",
  "vaiTro": "thanh-vien",
  "tenantId": "vip-group",
  "xacThuc": "session",
  "devMode": false
}
```

Không có bước nhập mật khẩu/MFA nào ở Brain; phiên được tạo từ ticket one-time + HMAC. `devMode=false` xác nhận không dựa vào header dev.

### d. Chat thật với prompt yêu cầu

Prompt gửi nguyên văn:

> “Xin chào VIP AI Brain. Hãy xác nhận mô hình AI Local đang xử lý yêu cầu này và cho tôi biết những chức năng hiện có thể sử dụng.”

`POST /api/chat` → **200**, envelope `ok=true`, `data`:

| Trường | Giá trị |
|---|---|
| `providerId` | `local` |
| `nhan` | `real` |
| `meta.provider` | `local` |
| `meta.model` | `qwen2.5:7b-instruct` |
| `meta.doTreMs` | ~2995 ms |
| `meta.tokenVao` / `tokenRa` | 62 / 263 |
| `meta.chiPhi` / `giaCo` | 0 / false |
| `taskId` | `T-G02-000021` |
| `traLoi` | không rỗng (893 ký tự trong lần chạy này) |

Trích đầu câu trả lời thật (không chỉnh sửa):

> “Xin chào! Tôi là Qwen, một trợ lý AI của Alibaba Cloud. Dù tên gọi của bạn gợi lên một mô hình AI cụ thể, tôi đang là trợ lý AI có khả năng xử lý yêu cầu của bạn thông qua nền tảng của Alibaba Cloud…”

**Lưu ý trung thực:** model thật tự nhận là Qwen/Alibaba, không xác nhận thương hiệu “VIP AI Brain”. Đây là hành vi thật của `qwen2.5:7b-instruct`; metadata `providerId=local`, `nhan=real`, `model=qwen2.5:7b-instruct` và task trong DB staging mới là bằng chứng kỹ thuật. Không sửa nội dung để “đẹp báo cáo”.

### e. Thu hồi quyền Brain — COWORK 403 và phiên Brain cũ 401

Đã chạy đúng trên `nhan-vien-01` (xem `AG04-revoke-nv01.json`):

| Bước | Kết quả |
|---|---|
| Login `nhan-vien-01`, mở Brain trước khi thu hồi | `/brain` 200; `/api/auth/toi` 200 |
| Super admin `anh-thanh` đăng nhập COWORK | 303 |
| `POST /tai-khoan/nhan-vien-01/phan-quyen` với `quyen_brain=block` (+ CSRF) | 303 |
| COWORK `/brain` của nhân viên | **403** |
| `/api/me` modules | không còn `brain` (`dashboard,tasks,knowledge,usage`) |
| Brain cũ `GET /api/auth/toi` | **401** `CHUA_DANG_NHAP` |
| DB Brain staging | 2 phiên `nhan-vien-01` đều `thu-hoi`; audit `COWORK: Thu hồi phiên` |
| Super admin trả `quyen_brain=default` | 303 |
| COWORK `/brain` sau trả quyền | **200**; modules có lại `brain` |
| `user_permissions` của nhân viên sau restore | rỗng (về default theo vai trò) |
| Relaunch + `/api/auth/toi` sau restore | 303 → 200, đúng user |

Cơ chế: `services.dat_quyen_module` (AG-03, **không sửa**) gọi `brain.thu_hoi_phien()` khi mất `brain.view`/`brain.use`; HMAC `cowork->brain` khớp secret staging. Đã kiểm chứng bằng HTTP thật, không mock.

### f. Chốt MFA với `anh-thanh`

| Bước | Kết quả |
|---|---|
| Login COWORK `anh-thanh` (mật khẩu đọc từ `secrets/owner-anh-thanh.txt`) | 303 |
| `/brain` | 200, có nút mở |
| `POST /brain/mo` + CSRF | 303 → `http://127.0.0.1:8892/cowork/vao?ticket=...` |
| Brain bridge trả | **403** `text/html` |
| Nội dung | có câu **“Chưa bỏ MFA cho tài khoản này”** và giải thích “chưa được mở qua COWORK” |
| Cookie `vip_session` | **không được set** |
| Brain `/api/auth/toi` khi không có phiên | **401** |
| `COWORK_BRIDGE_ALLOW_MFA_USERS` | vẫn **0** (không bật) |
| Shadow `anh-thanh` trong DB staging | **không tạo** (count 0) |
| Audit Brain | `anh-thanh · COWORK: Chặn mở phiên (MFA)` |

---

## 4. KIỂM TRA USER FIRST-TIME VÀ BACKFILL SHADOW CŨ

### 4.1. User first-time `nhan-vien-ctrl-01`

Controller đã test SSO trước đó bằng bridge **cũ**, nên shadow `nhan-vien-ctrl-01` đã tồn tại nhưng **không có** `project_permissions`. Để kiểm tra đúng điều kiện first-time, tôi đã xoá **chỉ trong DB staging** shadow/permission/session của user này (audit giữ nguyên), rồi đăng nhập lại:

- Bridge tự tạo shadow: `vaiTro=thanh-vien`, `trangThai=hoat-dong`, **không mật khẩu**.
- Bridge tự thêm `project_permissions`: `tenantId=vip-group`, `duAnId=tong-hop`, `quyen=doc`.
- `GET /api/auth/toi` 200 đúng user.
- `POST /api/chat` 200: `providerId=local`, `nhan=real`, model `qwen2.5:7b-instruct`, `taskId=T-G02-000022`, `traLoi` không rỗng.

`AG04-e2e.json` mục `first_time_user` ghi rõ: trước cleanup có shadow cũ; `cleanup_deleted`; sau launch có user `taoLuc` mới, permission `tong-hop/doc`, session mới.

### 4.2. Backfill shadow cũ **không xoá user**

Để chứng minh không phải “xoá rồi tạo lại mới chạy được”, tôi giữ nguyên user `nhan-vien-ctrl-01` (giữ `taoLuc`), chỉ xoá `project_permissions` và session, rồi mở Brain lại:

- Trước: user tồn tại, permission rỗng.
- Sau launch: bridge **backfill** đúng `tong-hop/doc`; `taoLuc` **giữ nguyên** (chứng minh không tạo lại user).
- `POST /api/chat` 200: `providerId=local`, `nhan=real`, model `qwen2.5:7b-instruct`, `taskId=T-G02-000023`.

Đây trả lời trực tiếp lỗi controller báo: user COWORK đã có shadow từ bridge cũ, chưa có project permission, nay được backfill và chat 200 — không cần xoá user.

---

## 5. TỆP ĐÃ SỬA / TẠO

| Tệp | Thay đổi |
|---|---|
| `scripts/provision_brain_staging.sh` | Quote `VIP_BRAIN_DB`, `MFA_SECRET_FILE`, `PYTHONPYCACHEPREFIX`; thêm cấu hình model local `qwen2.5:7b-instruct` trong DB staging; `CHO_PHEP_GOI_THAT=1` (staging, local-only); sửa tên script hướng dẫn cuối |
| `brain-staging/.env` | Quote 3 biến đường dẫn; `CHO_PHEP_GOI_THAT=1`; comment giải thích local-only |
| `brain-bridge/cowork_bridge.py` | (1) `_vai_tro_brain` fail-closed; (2) `_dam_bao_quyen_chat_chung` cấp `tong-hop/doc` khi tạo shadow + backfill có điều kiện; (3) docstring/comment giải thích phạm vi |
| `scripts/apply_bridge.py` | Import-check dùng DB tạm, không tạo `backend/vip-brain.db`, không đụng DB staging đang chạy; thêm `import os` |
| `tests/test_brain_ag04.py` | **Mới** — 14 test: ánh xạ vai trò, tạo shadow, backfill, không đụng native có mật khẩu/đã có quyền dự án, sai tenant |
| `brain-staging/**` | Runtime staging: DB bản sao, `providerConfig` local, permission test, xoá DB rác; không phải production |
| `cowork/brain.py`, `cowork/routers/brain_routes.py` | **Không sửa** — code hiện có đã đúng; E2E chứng minh hoạt động |
| `cowork/services.py`, templates, auth, Caddy/DNS | **Không sửa** |

---

## 6. KIỂM THỬ

```bash
cd "/Users/viporder/Library/CloudStorage/SynologyDrive-Macbook/VIP GROUP ID/cowork"
.venv/bin/python -m pytest -q
```

Kết quả: **81 test — 80 PASSED · 0 FAILED · 1 XPASS (không fail)**; `tests/test_brain_ag04.py`: **14 test PASSED**. Log: `evidence/AG04-pytest.txt`.

**Lưu ý ngoài vùng:** XPASS duy nhất là `tests/test_ui_ag01.py::test_route_khong_ton_tai_phai_tra_ve_trang_404_html`; lý do ghi trong test: route không khớp khiến Starlette trả JSON `{"detail":"Not Found"}` thay vì `404.html`, cần bắt `HTTPException` trong `cowork/main.py` — controller xử lý. Đây là lỗi ngoài vùng AG-04, không ảnh hưởng E2E Brain; báo để controller không bỏ sót.

Kiểm tra thêm:
- `sh -n` cho `provision_brain_staging.sh`, `start-brain-staging.sh`, `stop-brain-staging.sh`: OK.
- `py_compile` cho `brain-bridge/cowork_bridge.py`, `cowork/brain.py`, `cowork/brain_routes.py`, `scripts/apply_bridge.py`, `tests/test_brain_ag04.py`: OK.
- `source brain-staging/.env` trong shell sạch: `SOURCE_OK` (`AG04-checks.txt`).
- Không dùng mock/cloud: mọi chat nghiệm thu có `nhan=real`, `providerId=local`; `VIP_AI_LOCAL_ONLY=1`.

---

## 7. BẰNG CHỨNG

| Tệp | Nội dung |
|---|---|
| `evidence/AG04-e2e.json` | E2E a–f trên `nhan-vien-01` + first-time `nhan-vien-ctrl-01` + revoke/restore + MFA; có health/DB/model/flags; không có ticket/mật khẩu/cookie |
| `evidence/AG04-backfill.json` | Backfill shadow cũ `nhan-vien-ctrl-01`: giữ `taoLuc`, tự thêm `tong-hop/doc`, chat real |
| `evidence/AG04-revoke-nv01.json` | Đúng luồng e trên `nhan-vien-01`: block 303 → `/brain` 403 → Brain 401 → restore 303 → `/brain` 200 |
| `evidence/AG04-checks.txt` | Quote/source `.env`, health, PID/port, DB staging/integrity, hash bridge, model local, quota, không DB rác, permission shadow |
| `evidence/AG04-pytest.txt` | Log pytest cuối: 80 PASSED, 0 FAILED, 1 XPASS (ngoài vùng AG-04); 14/14 test AG-04 PASSED |
| `evidence/AG04-report.md` | Báo cáo này |

Không in mật khẩu, ticket, cookie hay `COWORK_SHARED_SECRET` trong bất kỳ tệp bằng chứng nào (đã quét chuỗi nhạy cảm).

---

## 8. RỦI RO / VIỆC CONTROLLER CẦN LÀM

1. **MFA secret staging đang thiếu:** `MFA_SECRET_FILE` trỏ `/Users/viporder/VIP-AI/brain/mfa_secret.txt`, file này **không tồn tại trên MacBook**. Chốt MFA của bridge vẫn đúng (403 trước khi đọc secret), nhưng nếu sau này đăng nhập trực tiếp Brain staging bằng tài khoản bật MFA, Brain sẽ fail-closed 503. Cần chủ dự án đặt secret đúng chỗ hoặc chỉnh đường dẫn; **không bật** `COWORK_BRIDGE_ALLOW_MFA_USERS`.
2. **`CHO_PHEP_GOI_THAT=1` là thay đổi có chủ đích trên staging** để có chat thật. Chốt chặn cloud thực tế là `VIP_AI_LOCAL_ONLY=1` trong `app/providers`; `NO_CLOUD=1` **không được mã Brain tham chiếu** (chỉ là dấu cấu hình). Không copy nguyên cấu hình này sang production nếu chưa review.
3. **Quota staging `tong-hop` đã nâng 10 → 100** do chạy lặp E2E (lượt trước bị `QUOTA_NGAY_VUOT` sau 10 task). Đây là dữ liệu staging, production không đổi. Nếu muốn quay lại 10, cần xoá/đặt lại task test hoặc chấp nhận E2E có thể chạm quota.
4. **Ánh xạ vai trò đã đổi:** COWORK `admin`/`department_manager` không còn là `quan-tri` Brain; nếu nghiệp vụ cần họ dùng màn quản trị Brain, phải làm cơ chế uỷ quyền riêng có kiểm soát. Đây là thay đổi bảo mật có chủ đích, cần controller review.
5. **Backfill chỉ áp dụng cho shadow “sạch”**: không mật khẩu Brain + chưa có bất kỳ `project_permissions`. Tài khoản native có mật khẩu hoặc đã có quyền dự án **không bị chạm** (có test). Nếu có shadow cũ đã được cấp một dự án khác nhưng thiếu `tong-hop`, bridge sẽ không tự thêm; cần xử lý dữ liệu riêng.
6. **Dữ liệu test trong staging:** các shadow `nhan-vien-01`, `nhan-vien-ctrl-01`, `nhan-vien-ctrl-02`, `qa-emp-*` và `project_permissions(tong-hop/doc)` là dữ liệu test/staging. Production không có các thay đổi này. `nhan-vien-01` ban đầu được thêm tay permission trong lúc chẩn đoán; sau đó đã xoá và cho bridge tự backfill lại — hiện quyền là do bridge tạo.
7. **Cổng COWORK:** đang dùng `8899` đúng như ưu tiên; **không** dùng server tạm `8901`. Nếu controller buộc phải chạy `8901`, phải đổi `COWORK_INTERNAL_URL` trong `brain-staging/.env` và restart staging, nếu không bridge sẽ gọi nhầm 8899.
8. **Re-provision:** `provision_brain_staging.sh` sẽ `rm -rf brain-staging` và tạo lại từ bản production; mọi shadow/permission/task test trong staging sẽ mất. Script đã tự cấu hình model + bridge, nhưng cần chạy lại `apply_bridge.py` (script provision đã gọi) và kiểm tra `COWORK_SHARED_SECRET` vẫn khớp `data/brain_secret.key`.
9. **Production:** không có thao tác nào lên `127.0.0.1:8891`, `vip-brain.db` production, Caddy/DNS/VPS; không deploy/push/git commit.

---

## 9. LỆNH CHÍNH ĐÃ CHẠY

```bash
# Sửa env + khởi động staging
./scripts/start-brain-staging.sh
curl -s http://127.0.0.1:8892/api/health
curl -s http://127.0.0.1:8892/api/cowork/suc-khoe

# Áp bridge + restart (không đụng 8899/8891)
.venv/bin/python scripts/apply_bridge.py brain-staging
./scripts/stop-brain-staging.sh
./scripts/start-brain-staging.sh

# Kiểm thử
.venv/bin/python -m pytest -q
.venv/bin/python /tmp/ag04_acceptance.py
.venv/bin/python /tmp/ag04_backfill.py
.venv/bin/python /tmp/ag04_revoke_nv01.py
```

(Không có lệnh nào trỏ tới `127.0.0.1:8891` hay DB production.)
