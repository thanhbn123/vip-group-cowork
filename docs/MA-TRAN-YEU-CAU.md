# MA TRẬN TRUY VẾT YÊU CẦU — COWORK

**Ngày:** 19/10/2026 · **Đã chốt sau khi 5 agent hoàn tất.** Full suite: 95 passed.

| # | Yêu cầu | Nơi triển khai | Kiểm chứng | Trạng thái |
|---|---|---|---|---|
| 1 | `anh-thanh` là Super Admin cao nhất | `cowork/services.py::tao_super_admin`; `rbac.bao_ve_super_admin`; UI chặn sửa | `test_quan_tri_khong_sua_duoc_super_admin`; UI | ✅ local |
| 2 | Super Admin tạo quản trị cấp dưới | `services.tao_nguoi_dung`, `rbac.kiem_tra_gan_vai_tro`; `/tai-khoan/tao-moi` | Tạo `quan-tri-01`; audit | ✅ local |
| 3 | Super Admin tạo trưởng ban | Cùng luồng tài khoản, vai trò `department_manager`, gán ban | Test agent/UI | ✅ local |
| 4 | Tạo nhân viên theo ban | `services.tao_nguoi_dung` yêu cầu ban cho employee; scope | Tạo `nhan-vien-01` bởi admin | ✅ local |
| 5 | Tạo ban/bộ phận | `services.tao_ban`; `/ban` | `test_*department*` (agent) | ✅ local |
| 6 | Cấp/thu hồi quyền | `dat_quyen_module`; `user_permissions` allow/deny | `test_thu_hoi_quyen_module_co_hieu_luc_ngay` | ✅ local |
| 7 | Quản lý module | Bảng `modules`; `/module-registry`; `cap_nhat_module` | Agent UI/test | ✅ local |
| 8 | Xem nhật ký hệ thống | `audit_log` append-only; `/nhat-ky`; CSV | `test_audit_append_only` | ✅ local |
| 9 | Quản trị cấp dưới chỉ trong phạm vi | `rbac.pham_vi_ban`, `co_the_quan_ly`; `admin_scopes` | `test_quan_tri_theo_ban_khong_thao_tac_ngoai_pham_vi` | ✅ local |
| 10 | Không tự nâng quyền | `kiem_tra_khong_tu_nang`, `co_the_gan_vai_tro`, subset grant | Agent AG-03 | ✅ local |
| 11 | Không sửa Super Admin | `bao_ve_super_admin`, `co_the_quan_ly` trả false | Test + DB check | ✅ local |
| 12 | Nhân viên đăng nhập bằng ID | `auth.dang_nhap`; cookie `cowork_session` | 14 test + login thật | ✅ local |
| 13 | Nhân viên chỉ thấy module được cấp | `rbac.module_hien_thi`; sidebar từ `request.state.modules` | `/api/me` = 5 module; 403 admin | ✅ local |
| 14 | Tenant isolation | `tenant_id` ở mọi truy vấn; `_target` lọc tenant | `test_cach_ly_tenant` | ✅ local |
| 15 | Audit logs | `audit.ghi`; trigger no update/delete | `test_audit_append_only`; UI | ✅ local |
| 16 | Session revocation | `auth.thu_hoi_phien`, `thu_hoi_cua_user`; admin UI | `test_thu_hoi_phien_chan_ngay`; UI | ✅ local |
| 17 | Partner | Vai trò `partner`, `partner_org`, `/doi-tac` | Agent UI | ✅ local |
| 18 | SSO COWORK → Brain | `brain.tao_ticket`, `brain-bridge/cowork_bridge.py`, `/cowork/vao` | Controller SSO + `tests/test_brain_ag04.py` | ✅ staging |
| 19 | Không đăng nhập/MFA lần hai | Brain tạo phiên native; owner COWORK MFA → bridge cho qua | `evidence/PRODUCTION-owner-brain-20261019.json` | ✅ production |
| 20 | Kiểm tra quyền tại backend Brain | Bridge từ chối ticket nếu thiếu `brain.use`/`brain.view`; Brain route tự kiểm | Controller + AG-04 | ✅ staging |
| 21 | Giữ AI Local trên Mac Studio | Ollama `qwen2.5:7b-instruct`; `providerId=local`, `nhan=real` | Task `T-G02-000003`; `localOnly` | ✅ staging |
| 22 | Không xây lại AI Brain | Không sửa DB/schema; bridge feature-flag | Snapshot production 7 users, DB ok | ✅ |
| 23 | Không tắt bảo vệ cũ sớm | `MFA_BAT=1`; owner COWORK MFA bật rồi mới `ALLOW_MFA_USERS=1` | owner Brain 200 + logout 401 | ✅ production |
| 24 | Không đụng DNS/public URL | DNS giữ nguyên; Caddy block thêm 19/10/2026, không đổi DNS | `docs/CAU-HINH-TEN-MIEN.md` | ✅ |
| 26 | MFA TOTP cho COWORK | Enroll + login challenge + 10 mã dự phòng + CLI reset | `tests/test_mfa_controller.py`, `evidence/PRODUCTION-mfa-smoke-20261019.json` | ✅ |
| 25 | Tên miền chính thức | `https://cowork.vipgroup.com.vn` live HTTPS + TLS | `evidence/PRODUCTION-DEPLOY-20261019.md` | ✅ |
| 26 | Không tự deploy/push | Không chạy deploy; Git local baseline | `git log` local | ✅ |
| 27 | Không kết nối dự án khác | Chỉ Brain; không thêm connector | Rà soát code | ✅ |

**Chú thích:** ✅ = đã chạy và có bằng chứng (local/staging hoặc production); ⏳ = còn lại.
**Bằng chứng cuối:** `evidence/FINAL-acceptance-20261019.json` · `evidence/FINAL-acceptance-report-20261019.md` · `evidence/controller-final-e2e.json`.

---

## KHOẢNG TRỐNG ĐÃ BIẾT (không được báo PASS production)

3. COWORK đã có MFA TOTP; owner production đã bật 19/10/2026.
4. ~~IP thật sau proxy Caddy~~ — đã vá (`COWORK_TIN_PROXY=1`, `web.ip_cua`); audit production ghi `14.190.214.49`.
5. Đăng xuất COWORK chưa thu hồi phiên Brain (nếu chủ dự án yêu cầu).
6. Brain production còn nợ cũ: `/api/settings` authz gap, header chưa persist — không do COWORK.
