# DEPLOY ARTIFACTS — ĐÃ DÙNG CHO GO-LIVE 19/10/2026

Bộ tệp này đã được dùng để go-live 3 cổng ngày 19/10/2026 (chủ dự án phê duyệt).
Xem biên bản `evidence/PRODUCTION-DEPLOY-20261019.md`; rollback `docs/ROLLBACK.md`.

## Tệp

| Tệp | Đích trên Mac Studio / VPS |
|---|---|
| `com.vipgroup.cowork.plist` | `~/Library/LaunchAgents/com.vipgroup.cowork.plist` |
| `com.vipgroup.cowork.tunnel-vps.plist` | `~/Library/LaunchAgents/com.vipgroup.cowork.tunnel-vps.plist` |
| `tunnel-vps.sh` | `~/VIP-AI/cowork/bin/tunnel-vps.sh` (chmod 700; khóa `id_ed25519_cowork_vps_tunnel`) |
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

## Ghi chú thực tế

- `/etc/caddy/Caddyfile` là bind mount **read-only**; sửa host file qua:
  `docker run --rm -i -v /srv/vip-staging-proxy:/work caddy:2-alpine sh -c 'cat >> /work/Caddyfile'`
  (sao lưu trước; validate + reload sau).
- Tunnel COWORK dùng khóa riêng `id_ed25519_cowork_vps_tunnel`, đã thêm `permitlisten="127.0.0.1:18835"` vào
  `~deploy/.ssh/authorized_keys`.

## Offsite COWORK

- `com.vipgroup.cowork.offsite.plist` chạy 03:40, gọi `~/VIP-AI/bin/backup-cowork-offsite.sh`.
- Script nguồn: `scripts/backup-cowork-offsite.sh`; cài:
  `cp scripts/backup-cowork-offsite.sh ~/VIP-AI/bin/ && cp deploy/com.vipgroup.cowork.offsite.plist ~/Library/LaunchAgents/`
  rồi `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vipgroup.cowork.offsite.plist`.
- Đích: `SAO LUU VPS/VIP-AI-COWORK`, mã hoá AES-256, retention 14.
