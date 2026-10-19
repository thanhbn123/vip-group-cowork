#!/usr/bin/env python3
"""Owner production: đăng nhập COWORK (MFA) → mở Brain không hỏi MFA lần hai → chat → logout thu hồi."""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from cowork import security

COWORK = "https://cowork.vipgroup.com.vn"
BRAIN = "https://ai.vipgroup.com.vn"
ROOT = Path(__file__).resolve().parent.parent
PW = (ROOT / "secrets" / "owner-anh-thanh.txt").read_text().strip()
MFA = (ROOT / "secrets" / "owner-mfa-anh-thanh.txt").read_text()
SECRET = re.search(r"Mã bí mật[^:]*:\s*([A-Z2-7]+)", MFA).group(1)


def csrf(html: str) -> str:
    return re.search(r'name="_csrf"\s+value="([^"]+)"', html).group(1)


def main() -> int:
    out = {}
    c = httpx.Client(follow_redirects=False, timeout=120)
    r = c.get(COWORK + "/dang-nhap")
    r = c.post(COWORK + "/dang-nhap", data={
        "userId": "anh-thanh", "matKhau": PW, "_csrf": csrf(r.text), "next": "/"})
    assert r.status_code == 303 and r.headers["location"].startswith("/dang-nhap/mfa")
    out["password_step"] = 303
    page = c.get(COWORK + "/dang-nhap/mfa")
    r = c.post(COWORK + "/dang-nhap/mfa", data={
        "_csrf": csrf(page.text), "next": "/", "ma": security.totp(SECRET)})
    assert r.status_code == 303 and r.headers["location"] == "/"
    out["mfa_step"] = 303
    assert c.get(COWORK + "/api/me").status_code == 200

    bp = c.get(COWORK + "/brain")
    assert bp.status_code == 200
    launch = c.post(COWORK + "/brain/mo", data={"_csrf": csrf(bp.text)})
    assert launch.status_code == 303, launch.status_code
    loc = launch.headers.get("location", "")
    assert loc.startswith(BRAIN + "/cowork/vao?ticket="), loc[:100]
    vao = c.get(loc)
    assert vao.status_code == 303, (vao.status_code, vao.text[:300])
    toi = c.get(BRAIN + "/api/auth/toi")
    assert toi.status_code == 200, (toi.status_code, toi.text[:300])
    out["brain_sso"] = {"vao": 303, "toi": 200}
    out["brain_user"] = toi.json()["data"]["userId"]

    chat = c.post(BRAIN + "/api/chat", json={
        "prompt": "Xin chào, hãy xác nhận mô hình AI Local đang trả lời và nêu 3 chức năng chính.",
        "modelId": "auto", "duAnId": "tong-hop"})
    assert chat.status_code == 200, (chat.status_code, chat.text[:300])
    d = chat.json().get("data") or {}
    meta = d.get("metadata") or d.get("meta") or {}
    out["chat"] = {"providerId": d.get("providerId"), "nhan": d.get("nhan"),
                   "model": meta.get("model"), "chiPhi": meta.get("chiPhi"),
                   "taskId": d.get("taskId"), "doDaiTraLoi": len(d.get("traLoi") or "")}
    assert d.get("providerId") == "local" and d.get("nhan") == "real"

    profile = c.get(COWORK + "/ho-so")
    lo = c.post(COWORK + "/dang-xuat", data={"_csrf": csrf(profile.text)})
    assert lo.status_code == 303
    out["logout"] = 303
    assert c.get(BRAIN + "/api/auth/toi").status_code == 401
    out["brain_revoked_on_logout"] = 401
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
