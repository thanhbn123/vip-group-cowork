#!/usr/bin/env python3
"""Bật MFA cho owner production và xác minh đăng nhập 2 lớp.

Chạy trên Mac Studio. Không in secret/mật khẩu; ghi file 0600 cho owner.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import httpx

from cowork import audit, auth, db, security

COWORK = "https://cowork.vipgroup.com.vn"
ROOT = Path(__file__).resolve().parent.parent
OWNER = "anh-thanh"
PW = (ROOT / "secrets" / "owner-anh-thanh.txt").read_text().strip()
FILE = ROOT / "secrets" / "owner-mfa-anh-thanh.txt"


def csrf(html: str) -> str:
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html or "")
    if not m:
        raise RuntimeError("Không thấy CSRF")
    return m.group(1)


def reset_mfa(conn) -> None:
    conn.execute("UPDATE users SET mfa_enabled=0, mfa_secret=NULL WHERE id=?", (OWNER,))
    conn.execute("DELETE FROM mfa_backup_codes WHERE user_id=?", (OWNER,))
    conn.execute("DELETE FROM mfa_challenges WHERE user_id=?", (OWNER,))
    conn.commit()


def verify(secret: str) -> dict:
    c = httpx.Client(follow_redirects=False, timeout=30)
    r = c.get(COWORK + "/dang-nhap")
    r = c.post(COWORK + "/dang-nhap", data={
        "userId": OWNER, "matKhau": PW, "_csrf": csrf(r.text), "next": "/"})
    assert r.status_code == 303 and r.headers["location"].startswith("/dang-nhap/mfa"), \
        f"login không chuyển MFA: {r.status_code} {r.headers.get('location')}"
    page = c.get(COWORK + "/dang-nhap/mfa")
    assert page.status_code == 200
    r = c.post(COWORK + "/dang-nhap/mfa", data={
        "_csrf": csrf(page.text), "next": "/", "ma": security.totp(secret)})
    assert r.status_code == 303 and r.headers["location"] == "/", \
        f"MFA không qua: {r.status_code} {r.headers.get('location')}"
    assert c.get(COWORK + "/api/me").status_code == 200
    # Thu hồi phiên test
    profile = c.get(COWORK + "/ho-so")
    c.post(COWORK + "/dang-xuat", data={"_csrf": csrf(profile.text)})
    return {"login_mfa": 303, "api_me": 200, "logout": 303}


def main() -> int:
    conn = db.connect()
    try:
        owner = auth.nguoi_dung_day_du(conn, OWNER)
        if not owner:
            raise SystemExit("Không thấy owner")
        secret = security.tao_bi_mat_totp()
        codes = auth.bat_mfa(conn, owner, secret, security.totp(secret), PW)
        audit.ghi(conn, owner, "mfa.enable", target_type="user", target_id=OWNER,
                  detail={"nguon": "bootstrap-owner", "soMaDuPhong": len(codes)})
        uri = security.otpauth_uri(secret, OWNER)
        noi_dung = f"""VIP GROUP COWORK — XÁC THỰC 2 LỚP CHO OWNER
Tạo lúc: {datetime.now().astimezone().isoformat(timespec='seconds')}
Tài khoản: {OWNER}
Mã bí mật (nhập thủ công vào authenticator): {secret}
URI: {uri}

MÃ DỰ PHÒNG (mỗi mã dùng một lần):
""" + "\n".join(f"- {c}" for c in codes) + f"""

HƯỚNG DẪN
1. Mở Google Authenticator / Authy / 1Password → Add account → Enter setup key.
2. Dán mã bí mật ở trên, chọn Time-based, 6 digits, 30 seconds.
3. Đăng nhập COWORK, nhập mã 6 số.
4. Lưu file này ở nơi an toàn; không gửi qua chat/email không mã hoá.

MẤT THIẾT BỊ
- Dùng một mã dự phòng ở trên, hoặc chạy trên Mac Studio:
  cd ~/VIP-AI/cowork && .venv/bin/python -m cowork.cli mfa-reset --id {OWNER}
"""
        FILE.write_text(noi_dung, encoding="utf-8")
        FILE.chmod(0o600)
    finally:
        conn.close()

    try:
        kq = verify(secret)
    except Exception as e:
        conn = db.connect()
        try:
            reset_mfa(conn)
        finally:
            conn.close()
        FILE.unlink(missing_ok=True)
        print(json.dumps({"ok": False, "loi": str(e)[:300], "daReset": True}, ensure_ascii=False))
        return 1

    conn = db.connect()
    try:
        active = db.scalar(conn, "SELECT COUNT(*) FROM users WHERE id=? AND mfa_enabled=1", (OWNER,))
        con_lai = auth.ma_du_phong_con_lai(conn, OWNER)
    finally:
        conn.close()
    print(json.dumps({
        "ok": True, "owner": OWNER, "mfa_enabled": bool(active),
        "backup_codes": con_lai, "file": str(FILE), **kq,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
