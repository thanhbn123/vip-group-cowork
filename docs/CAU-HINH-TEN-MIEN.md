# KIỂM TRA CẤU HÌNH TÊN MIỀN — COWORK & AI BRAIN

**Ngày:** 19/10/2026 · **Trạng thái:** ĐÃ KIỂM TRA, CHƯA THAY ĐỔI CẤU HÌNH
**Quyết định chính thức:** COWORK = `https://cowork.vipgroup.com.vn` · Brain = `https://ai.vipgroup.com.vn`

---

## 1. KẾT QUẢ KIỂM TRA

| Hạng mục | Kết quả | Ghi chú |
|---|---|---|
| DNS `cowork.vipgroup.com.vn` | ✅ A → `160.22.170.20` | Đã lan truyền; Google DNS `8.8.8.8` trả cùng IP. Không có AAAA/CNAME. |
| DNS `ai.vipgroup.com.vn` | ✅ A → `160.22.170.20` | Giữ nguyên. |
| HTTP `cowork` | ⚠️ `308` → `https://cowork...` | Caddy trả redirect mặc định; **chưa có site block**. |
| HTTPS `cowork` | ❌ `TLS alert internal error`, không có cert | Caddy chưa cấu hình tên này nên không xin được chứng chỉ. |
| HTTPS `ai` | ✅ `200`, cert Let's Encrypt | `CN=ai.vipgroup.com.vn`, hạn 16/01/2027. |
| Caddy | ✅ `v2.11.4`, container `vip-staging-caddy`, network host | Cấu hình `/srv/vip-staging-proxy/Caddyfile` (root), mount `/etc/caddy/Caddyfile`. |
| Danh sách domain Caddy quản lý | `viporder.com.vn`, `hq`, `ai`, `vtp.staging`, `www.viporder`, `cpn`, `qua`, `hub.staging`, `member...` | **Không có `cowork`**. |
| Cổng 80/443 | ✅ đang mở công khai | Đủ điều kiện HTTP-01 challenge. |
| Tunnel Brain | ✅ `127.0.0.1:18834` → Mac Studio `127.0.0.1:8891` | `/api/health` trả `200`, DB `ok`. |
| Cổng dự kiến cho COWORK | `127.0.0.1:18835` — **đang trống** | Dùng tunnel riêng, không đụng 18834 của Brain. |
| Quyền quản trị Caddy | `deploy` không có sudo; nhưng thuộc group `docker` | Có thể đọc/ghi Caddyfile qua `docker exec` (root trong container). **Chưa thao tác.** |
| Firewall | Không đọc được `ufw` bằng `deploy` | 80/443 đã truy cập được từ Internet nên firewall đang cho qua. |

**Kết luận:** DNS đã đúng, không cần đổi DNS. Thiếu **một site block Caddy** cho `cowork.vipgroup.com.vn` và **một tunnel** trỏ về dịch vụ COWORK. Chưa có thay đổi nào được áp dụng.

---

## 2. HIỆN TRẠNG KHỐI AI TRONG CADDY (NGUYÊN VĂN RÚT GỌN)

```caddy
ai.vipgroup.com.vn {
    encode zstd gzip
    header {
        X-Robots-Tag "noindex, nofollow"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }
    @quan_tri path /api/settings* /api/budgets* /api/providers* /api/ops* /api/code-agent*
    handle @quan_tri {
        @khong_duoc not remote_ip 127.0.0.1/32 14.190.214.49/32 100.64.0.0/10
        respond @khong_duoc "Không có quyền truy cập quản trị." 403
        reverse_proxy 127.0.0.1:18834 {
            header_up X-Real-IP {remote_host}
            header_down Set-Cookie "^(.*)$" "$1; Secure"
        }
    }
    handle {
        reverse_proxy 127.0.0.1:18834 {
            header_up X-Real-IP {remote_host}
            header_down Set-Cookie "^(.*)$" "$1; Secure"
        }
    }
    log {
        output file /data/access-vip-ai-brain.log { roll_size 10mb roll_keep 5 }
    }
}
```

- Brain vẫn chạy độc lập trên Mac Studio, chỉ nghe `127.0.0.1:8891`; VPS không mở trực tiếp cổng Brain.
- COWORK sẽ dùng **tunnel riêng** `18835`, không dùng chung 18834.

---

## 3. KHỐI CADDY SOẠN SẴN CHO COWORK — CHƯA ÁP DỤNG

```caddy
# VIP GROUP COWORK — cổng đăng nhập và làm việc tập trung.
# Đích: /srv/vip-staging-proxy/Caddyfile (root giữ). Áp dụng SAU khi kiểm thử bảo mật đạt.
cowork.vipgroup.com.vn {
    encode zstd gzip
    header {
        X-Robots-Tag "noindex, nofollow"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }
    reverse_proxy 127.0.0.1:18835 {
        header_up X-Real-IP {remote_host}
        header_down Set-Cookie "^(.*)$" "$1; Secure"
    }
    log {
        output file /data/access-cowork.log {
            roll_size 10mb
            roll_keep 5
        }
    }
}
```

**Ghi chú kỹ thuật:**
- COWORK tự đặt CSP, HSTS, X-Frame-Options; Caddy chỉ thêm `noindex`, `nosniff`, `Referrer-Policy`, ẩn `Server` và ép `Secure` cho cookie.
- `X-Forwarded-Proto` do Caddy gửi; COWORK dùng nó để bật HSTS và cờ `Secure`.
- Không cần đổi DNS: bản ghi A đã đúng.
- Chứng chỉ sẽ được Caddy tự xin bằng HTTP-01 sau khi reload; cổng 80 đang mở.

---

## 4. QUY TRÌNH ÁP DỤNG (KHI ĐƯỢC DUYỆT)

```bash
# 1. Sao lưu
cp /srv/vip-staging-proxy/Caddyfile \
   /srv/vip-staging-proxy/Caddyfile.bak-before-cowork-$(date +%Y%m%d-%H%M)

# 2. Dán khối §3 vào cuối Caddyfile
# 3. Kiểm tra cú pháp
docker exec vip-staging-caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# 4. Nạp lại không downtime
docker exec vip-staging-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
# 5. Kiểm tra
curl -I https://cowork.vipgroup.com.vn/
echo | openssl s_client -connect cowork.vipgroup.com.vn:443 -servername cowork.vipgroup.com.vn 2>/dev/null | openssl x509 -noout -subject -dates
```

**Rollback:**
```bash
cp /srv/vip-staging-proxy/Caddyfile.bak-before-cowork-<thời-điểm> \
   /srv/vip-staging-proxy/Caddyfile
docker exec vip-staging-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```
DNS không đổi nên rollback chỉ gồm Caddyfile + reload.

---

## 5. ĐIỀU KIỆN TRƯỚC KHI ÁP DỤNG

- [ ] COWORK chạy ổn định trên Mac Studio, cổng `127.0.0.1:8899`.
- [ ] Tunnel `com.vipai.cowork.tunnel-vps` → `127.0.0.1:18835` hoạt động.
- [ ] Bộ kiểm thử bảo mật COWORK đạt: auth, CSRF, rate limit, RBAC, tenant, session revocation.
- [ ] Kiểm thử SSO COWORK → Brain trên staging đạt; MFA Brain vẫn bật cho đăng nhập trực tiếp.
- [ ] Có bản sao lưu Caddyfile và kịch bản rollback đã chạy thử.
- [ ] Chủ dự án phê duyệt.

**Chưa có mục nào trong danh sách trên được tự động áp dụng.**
