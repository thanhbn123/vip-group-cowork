# BIÊN BẢN CUTOVER PRODUCTION → VPS

**Ngày:** 19/10/2026 · **Phê duyệt:** chủ dự án “duyệt cutover production sang VPS”
**Kết quả:** ✅ COWORK production chạy trên VPS; Caddy trỏ 8899; Brain gọi COWORK public; nghiệm thu 8/8.

---

## 1. TRƯỚC CUTOVER

| Hạng mục | Giá trị |
|---|---|
| COWORK | Studio `127.0.0.1:8899`, Caddy → tunnel `18835` |
| DB production | 7 user · 109 audit · schema 2 |
| Backup trước cutover | `cowork-20261019-202502.db` (integrity ok) |
| Caddy hash | `eea7ed56…d86f` (upstream 18835) |
| Brain internal | `COWORK_INTERNAL_URL=http://127.0.0.1:8899` |

## 2. ĐÃ LÀM

1. **VPS**: copy DB backup mới + `secret.key` + `brain_secret.key`; cấu hình production:
   - `COWORK_PUBLIC_URL=https://cowork.vipgroup.com.vn`
   - `COWORK_INTERNAL_URL=https://cowork.vipgroup.com.vn`
   - `COWORK_COOKIE_SECURE=1`, `COWORK_TIN_PROXY=1`
   - `COWORK_BRAIN_BASE_URL=https://ai.vipgroup.com.vn`, `BRAIN_ENABLED=1`
2. **Brain**: `COWORK_INTERNAL_URL=https://cowork.vipgroup.com.vn`; restart backend; health/bridge OK.
3. **Caddy**: upstream `127.0.0.1:18835` → `127.0.0.1:8899`; restart container để nhận file mới
   (file bind-mount bị đổi inode khi `sed -i`); validate/reload OK.
4. **Nghiệm thu**: 8/8 PASS trên VPS, task `T-G02-000041` local/real, 243 ký tự.
5. **Owner smoke**: login 303 → `/`; SSO 303 → Brain `anh-thanh`; chat `T-G02-000042` local/real; logout thu hồi Brain 401.
6. **Backup**:
   - VPS local cron **03:20**, bản `cowork-20261019-203203.db`, users 11/audit 135.
   - Offsite VPS → Synology **03:50**, file `.enc` 256K; chạy cuối 20:34: `cowork-vps-20261019-203422.db.enc`, users 11/schema 2.
   - Studio local backup + offsite cũ đã tắt.

## 3. TRẠNG THÁI SAU CUTOVER

| Hạng mục | Giá trị |
|---|---|
| Public COWORK | `https://cowork.vipgroup.com.vn` → VPS `127.0.0.1:8899` |
| VPS container | `cowork-staging` — healthy, restart unless-stopped |
| DB VPS | 11 user (chỉ owner active), 135 audit, schema 2 |
| Caddy hash | `c0ae5314…74ad` (upstream 8899) |
| Brain internal | `https://cowork.vipgroup.com.vn` |
| Nghiệm thu | 8/8 PASS |
| Backup local VPS | `/srv/vip-staging/cowork-backups/` |
| Offsite | `SAO LUU VPS/VIP-AI-COWORK-VPS/cowork-vps-*.db.enc` |

## 4. BACKUP / ROLLBACK

- Caddy trước cutover: `~/Caddyfile.bak-before-cutover-20261019-202511.txt` + `/data/Caddyfile.bak-before-cutover-20261019-202511`.
- Brain trước cutover: `~/VIP-AI/backups/brain-env-before-cutover-20261019-202512`.
- DB trước cutover: `cowork-20261019-202502.db`; DB sau cutover: `cowork-20261019-203203.db`.
- Rollback:
  1. Copy DB VPS hiện tại về Studio nếu muốn giữ dữ liệu sau cutover.
  2. Caddy `8899` → `18835` (sửa file + **restart** container), validate.
  3. Brain `COWORK_INTERNAL_URL=http://127.0.0.1:8899`, restart.
  4. Bật lại backup/offsite Studio; kiểm tra.
- Tunnel 18835 vẫn chạy, sẵn sàng rollback.

## 5. LƯU Ý

- **Quota Brain**: `tong-hop` từ 10 → 100 task/ngày vì B7 gặp `QUOTA_NGAY_VUOT`; backup DB
  `~/VIP-AI/brain/backups/vip-brain-before-quota-20261019-202645.db`.
- **MFA owner đang tắt** sau lần reset khôi phục; nên bật lại `/ho-so/mfa`.
- Cửa sổ dữ liệu: backup lúc 20:25:02; cutover 20:26; ghi chú nếu có thay đổi trong khoảng này.
- Caddyfile bind-mount: sửa `sed -i` tạo inode mới → phải **restart Caddy**, reload đơn thuần vẫn đọc file cũ.
- Studio vẫn chạy COWORK cũ làm fallback; không nhận traffic public.
