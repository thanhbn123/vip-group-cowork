#!/bin/sh
# Tunnel COWORK Mac Studio → VPS. DÁN vào ~/VIP-AI/cowork/bin/tunnel-vps.sh.
# Chưa chạy. Cổng 18835 tách khỏi 18834 của Brain.
exec ssh -N \
  -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
  -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/Users/macstudio/.ssh/vipai_vps_known_hosts \
  -i /Users/macstudio/.ssh/id_ed25519_vipai_vps_tunnel_studio \
  -R 127.0.0.1:18835:127.0.0.1:8899 deploy@160.22.170.20
