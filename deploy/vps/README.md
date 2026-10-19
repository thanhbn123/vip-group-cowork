# COWORK — deploy staging trên VPS

Mục tiêu: dựng **bản staging** trên VPS cổng `127.0.0.1:8899`, dùng bản copy DB production,
**không đổi Caddy/Brain production**. Sau khi kiểm tra đạt mới bàn giao cutover.

## Yêu cầu
- Docker + Docker Compose (VPS đã có).
- Cổng 8899 trống.
- `data/` chứa `cowork.db`, `secret.key`, `brain_secret.key` (copy từ Studio, 0600).
- `.env.staging` từ `.env.staging.example`; staging để `COWORK_BRAIN_ENABLED=0` vì Brain
  production đang trỏ `COWORK_INTERNAL_URL` về Studio.

## Chạy
```bash
cd /srv/vip-staging/cowork
cp deploy/vps/.env.staging.example deploy/vps/.env.staging
# sửa .env.staging nếu cần
mkdir -p deploy/vps/data && chmod 700 deploy/vps/data
# copy dữ liệu vào deploy/vps/data/
docker run --rm -v "$PWD/deploy/vps/data:/data" alpine:3.20 \
  chown -R 10001:10001 /data
docker compose -f deploy/vps/docker-compose.yml up -d --build
curl -s http://127.0.0.1:8899/api/health
```

## Kiểm tra
- `/api/health` 200, `db=ok`.
- Đăng nhập owner (MFA staging tùy DB copy), `/api/me` 200.
- `docker ps` healthy; log không lỗi.

## Cutover (chưa làm)
Chỉ sau khi chủ dự án duyệt:
1. Caddy đổi upstream `cowork` từ `127.0.0.1:18835` sang `127.0.0.1:8899`.
2. Brain `.env` đổi `COWORK_INTERNAL_URL=https://cowork.vipgroup.com.vn`.
3. Chuyển backup/offsite sang VPS hoặc giữ Studio làm bản dự phòng.
