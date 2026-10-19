#!/usr/bin/env python3
"""Smoke MFA production (chạy trên Mac Studio): tạo admin, bật MFA, logout, login 2 lớp, archive."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime

import httpx

COWORK = "https://cowork.vipgroup.com.vn"
OWNER = os.environ.get("COWORK_OWNER_PASSWORD", "")
TAG = datetime.now().strftime("%H%M%S")


def csrf(html: str) -> str:
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html or "")
    if not m:
        raise RuntimeError("Không thấy CSRF")
    return m.group(1)


def c() -> httpx.Client:
    return httpx.Client(follow_redirects=False, timeout=60,
                        headers={"User-Agent": "COWORK-mfa-smoke/1.0"})


def login(cl: httpx.Client, uid: str, pw: str) -> httpx.Response:
    r = cl.get(COWORK + "/dang-nhap")
    return cl.post(COWORK + "/dang-nhap", data={
        "userId": uid, "matKhau": pw, "_csrf": csrf(r.text), "next": "/"})


def main() -> int:
    if not OWNER:
        raise SystemExit("Thiếu COWORK_OWNER_PASSWORD")
    out = {"tag": TAG, "steps": {}}
    owner = c()
    assert login(owner, "anh-thanh", OWNER).status_code == 303

    uid = f"prod-mfa-{TAG}"
    pw = "Mfa!" + secrets.token_urlsafe(10)
    page = owner.get(COWORK + "/tai-khoan/tao-moi")
    r = owner.post(COWORK + "/tai-khoan/tao-moi", data={
        "_csrf": csrf(page.text), "id": uid, "display_name": "QA MFA",
        "role_code": "admin", "department_id": "ban-dieu-hanh",
        "scope_mode": "tenant", "password": pw,
    })
    if r.status_code != 200 or "Đã tạo tài khoản" not in r.text:
        raise RuntimeError(f"create admin {r.status_code}: {r.text[:300]}")
    out["steps"]["create_admin"] = 200

    admin = c()
    assert login(admin, uid, pw).status_code == 303
    assert admin.get(COWORK + "/api/me").status_code == 200
    out["steps"]["login_before_mfa"] = 303

    setup = admin.get(COWORK + "/ho-so/mfa")
    assert setup.status_code == 200 and "Bật xác thực 2 lớp" in setup.text
    secret = re.search(r'id="mfa-secret">([^<]+)</code>', setup.text).group(1).strip()
    from cowork import security
    r = admin.post(COWORK + "/ho-so/mfa/bat", data={
        "_csrf": csrf(setup.text), "secret": secret,
        "ma": security.totp(secret), "matKhau": pw}, follow_redirects=False)
    assert r.status_code == 200 and "Lưu 10 mã này" in r.text, r.text[:300]
    out["steps"]["enable_mfa"] = 200
    out["secret_len"] = len(secret)

    profile = admin.get(COWORK + "/ho-so")
    admin.post(COWORK + "/dang-xuat", data={"_csrf": csrf(profile.text)})
    admin.cookies.clear()
    out["steps"]["logout"] = 303

    r = login(admin, uid, pw)
    assert r.status_code == 303 and r.headers["location"].startswith("/dang-nhap/mfa")
    out["steps"]["password_only_redirect"] = r.headers["location"]
    mfa_page = admin.get(COWORK + "/dang-nhap/mfa")
    assert mfa_page.status_code == 200
    r = admin.post(COWORK + "/dang-nhap/mfa", data={
        "_csrf": csrf(mfa_page.text), "next": "/", "ma": security.totp(secret)},
        follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert admin.get(COWORK + "/api/me").status_code == 200
    out["steps"]["login_with_totp"] = 303

    detail = owner.get(COWORK + f"/tai-khoan/{uid}")
    r = owner.post(COWORK + f"/tai-khoan/{uid}/luu-tru",
                   data={"_csrf": csrf(detail.text)})
    assert r.status_code == 303
    out["steps"]["archive"] = 303
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
