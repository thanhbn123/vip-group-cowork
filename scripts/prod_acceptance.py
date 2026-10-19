#!/usr/bin/env python3
"""Nghiệm thu 8 bước trên PRODUCTION (thật, không mock).

Chạy trên Mac Studio: đọc mật khẩu + MFA owner tại chỗ; tạo admin → nhân viên →
SSO Brain → chat local → thu hồi → archive. Không in mật khẩu/ticket/cookie.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from pathlib import Path

import httpx

from cowork import security

BASE = "https://cowork.vipgroup.com.vn"
BRAIN = "https://ai.vipgroup.com.vn"
ROOT = Path(__file__).resolve().parent.parent
TAG = datetime.now().strftime("%H%M%S")
OUT = ROOT / "evidence" / "PRODUCTION-acceptance-20261019.json"


def csrf(html: str) -> str:
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html or "")
    if not m:
        raise RuntimeError("Không thấy CSRF")
    return m.group(1)


def c() -> httpx.Client:
    return httpx.Client(follow_redirects=False, timeout=120,
                        headers={"User-Agent": "COWORK-prod-acceptance/1.0"})


def login_owner(cl: httpx.Client) -> None:
    pw = (ROOT / "secrets" / "owner-anh-thanh.txt").read_text().strip()
    mfa = (ROOT / "secrets" / "owner-mfa-anh-thanh.txt").read_text()
    secret = re.search(r"Mã bí mật[^:]*:\s*([A-Z2-7]+)", mfa).group(1)
    r = cl.get(BASE + "/dang-nhap")
    r = cl.post(BASE + "/dang-nhap", data={
        "userId": "anh-thanh", "matKhau": pw, "_csrf": csrf(r.text), "next": "/"})
    if r.status_code == 303 and r.headers["location"].startswith("/dang-nhap/mfa"):
        page = cl.get(BASE + "/dang-nhap/mfa")
        r = cl.post(BASE + "/dang-nhap/mfa", data={
            "_csrf": csrf(page.text), "next": "/", "ma": security.totp(secret)})
    assert r.status_code == 303 and r.headers["location"] == "/", (r.status_code, r.text[:200])
    assert cl.get(BASE + "/api/me").status_code == 200


def login(cl: httpx.Client, uid: str, pw: str) -> None:
    r = cl.get(BASE + "/dang-nhap")
    r = cl.post(BASE + "/dang-nhap", data={
        "userId": uid, "matKhau": pw, "_csrf": csrf(r.text), "next": "/"})
    assert r.status_code == 303 and r.headers["location"] == "/", (uid, r.status_code, r.text[:200])
    assert cl.get(BASE + "/api/me").status_code == 200


def main() -> int:
    out = {"meta": {"batDau": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "base": BASE, "brain": BRAIN, "tag": TAG}, "buoc": {}}
    owner = c()
    login_owner(owner)
    out["buoc"]["B1"] = {"status": "PASS", "moTa": "Owner đăng nhập COWORK + MFA"}

    admin_id = f"prod-accept-admin-{TAG}"
    admin_pw = "Ad!" + secrets.token_urlsafe(10)
    page = owner.get(BASE + "/tai-khoan/tao-moi")
    r = owner.post(BASE + "/tai-khoan/tao-moi", data={
        "_csrf": csrf(page.text), "id": admin_id, "display_name": "QA Accept Admin",
        "role_code": "admin", "department_id": "ban-dieu-hanh",
        "scope_mode": "tenant", "password": admin_pw})
    assert r.status_code == 200 and "Đã tạo tài khoản" in r.text, r.text[:300]
    out["buoc"]["B2"] = {"status": "PASS", "moTa": "Owner tạo quản trị cấp dưới",
                         "id": admin_id}

    admin = c()
    login(admin, admin_id, admin_pw)
    emp_id = f"prod-accept-emp-{TAG}"
    emp_pw = "Nv!" + secrets.token_urlsafe(10)
    page = admin.get(BASE + "/tai-khoan/tao-moi")
    r = admin.post(BASE + "/tai-khoan/tao-moi", data={
        "_csrf": csrf(page.text), "id": emp_id, "display_name": "QA Accept Employee",
        "role_code": "employee", "department_id": "kinh-doanh", "password": emp_pw})
    assert r.status_code == 200 and "Đã tạo tài khoản" in r.text, r.text[:300]
    out["buoc"]["B3"] = {"status": "PASS", "moTa": "Quản trị tạo nhân viên Ban Kinh doanh",
                         "id": emp_id}

    emp = c()
    login(emp, emp_id, emp_pw)
    me = emp.get(BASE + "/api/me").json()["data"]
    assert me["modules"] == ["dashboard", "brain", "tasks", "knowledge", "usage"], me["modules"]
    assert emp.get(BASE + "/tai-khoan").status_code == 403
    out["buoc"]["B4"] = {"status": "PASS", "moTa": "Nhân viên đăng nhập"}
    out["buoc"]["B5"] = {"status": "PASS", "moTa": "Chỉ 5 module; route admin 403",
                         "modules": me["modules"]}

    bp = emp.get(BASE + "/brain")
    launch = emp.post(BASE + "/brain/mo", data={"_csrf": csrf(bp.text)})
    assert launch.status_code == 303
    vao = emp.get(launch.headers["location"])
    assert vao.status_code == 303, (vao.status_code, vao.text[:200])
    toi = emp.get(BRAIN + "/api/auth/toi")
    assert toi.status_code == 200, (toi.status_code, toi.text[:200])
    out["buoc"]["B6"] = {"status": "PASS", "moTa": "SSO Brain một lần",
                         "brainUser": toi.json()["data"]["userId"]}

    chat = emp.post(BRAIN + "/api/chat", json={
        "prompt": "Xin chào VIP AI Brain. Hãy xác nhận mô hình AI Local đang xử lý yêu cầu này.",
        "modelId": "auto", "duAnId": "tong-hop"})
    assert chat.status_code == 200, (chat.status_code, chat.text[:200])
    d = chat.json().get("data") or {}
    meta = d.get("metadata") or d.get("meta") or {}
    assert d.get("providerId") == "local" and d.get("nhan") == "real"
    out["buoc"]["B7"] = {"status": "PASS", "moTa": "Chat local thật",
                         "providerId": d.get("providerId"), "nhan": d.get("nhan"),
                         "model": meta.get("model"), "chiPhi": meta.get("chiPhi"),
                         "taskId": d.get("taskId"), "doDaiTraLoi": len(d.get("traLoi") or "")}

    pp = owner.get(BASE + f"/tai-khoan/{emp_id}/phan-quyen")
    rv = owner.post(BASE + f"/tai-khoan/{emp_id}/phan-quyen", data={
        "_csrf": csrf(pp.text), "quyen_brain": "block"})
    assert rv.status_code == 303
    assert emp.get(BASE + "/brain").status_code == 403
    assert emp.get(BRAIN + "/api/auth/toi").status_code == 401
    pp2 = owner.get(BASE + f"/tai-khoan/{emp_id}/phan-quyen")
    rs = owner.post(BASE + f"/tai-khoan/{emp_id}/phan-quyen", data={
        "_csrf": csrf(pp2.text), "quyen_brain": "default"})
    assert rs.status_code == 303 and emp.get(BASE + "/brain").status_code == 200
    out["buoc"]["B8"] = {"status": "PASS", "moTa": "Thu hồi Brain 403/401, cấp lại 200"}

    # Dọn tài khoản test: archive employee rồi admin
    for uid in (emp_id, admin_id):
        detail = owner.get(BASE + f"/tai-khoan/{uid}")
        r = owner.post(BASE + f"/tai-khoan/{uid}/luu-tru",
                       data={"_csrf": csrf(detail.text)})
        assert r.status_code == 303, (uid, r.status_code)
    out["meta"]["ketThuc"] = datetime.now().astimezone().isoformat(timespec="seconds")
    out["meta"]["ketLuan"] = "PASS 8/8"
    out["meta"]["daDon"] = [emp_id, admin_id]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
