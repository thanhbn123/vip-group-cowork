# DEPLOY ARTIFACTS — CHƯA ÁP DỤNG

Bộ tệp này là **bản soạn sẵn** cho production, không phải lệnh đã chạy.
Chỉ dùng sau khi chủ dự án phê duyệt và đã đọc `docs/TRIEN-KHAI-PRODUCTION.md`, `docs/ROLLBACK.md`.

## Tệp

| Tệp | Đích trên Mac Studio / VPS |
|---|---|
| `com.vipgroup.cowork.plist` | `~/Library/LaunchAgents/com.vipgroup.cowork.plist` |
| `com.vipgroup.cowork.tunnel-vps.plist` | `~/Library/LaunchAgents/com.vipgroup.cowork.tunnel-vps.plist` |
| `tunnel-vps.sh` | `~/VIP-AI/cowork/bin/tunnel-vps.sh` (chmod 700) |
| `Caddyfile.cowork` | dán vào `/srv/vip-staging-proxy/Caddyfile`, reload Caddy |

## Thứ tự

1. COWORK chạy `127.0.0.1:8899` trên Mac Studio (LaunchAgent).
2. Tunnel `18835` hoạt động; kiểm tra từ VPS `curl 127.0.0.1:18835/api/health`.
3. Sao lưu Caddyfile → dán khối → `caddy validate` → `caddy reload`.
4. TLS tự cấp; kiểm tra `openssl s_client`.
5. Áp bridge Brain **sau cùng**, có phê duyệt riêng; giữ `COWORK_BRIDGE_ALLOW_MFA_USERS=0`.

## Không làm

- Không đổi DNS (đã đúng).
- Không sửa block `ai.vipgroup.com.vn` hay tunnel `18834`.
- Không bật `ALLOW_MFA_USERS`/tắt MFA trước nghiệm thu.
- Không chạy script này khi chưa có phê duyệt.

## Rollback

Xem `docs/ROLLBACK.md`; Caddy luôn sao lưu trước khi sửa:
```bash
cp /srv/vip-staging-proxy/Caddyfile \
   /srv/vip-staging-proxy/Caddyfile.bak-before-cowork-$(date +%Y%m%d-%H%M)
```
