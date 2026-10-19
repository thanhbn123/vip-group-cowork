#!/usr/bin/env python3
"""Smoke test production COWORK ↔ Brain. Chạy trên Mac Studio (đọc mật khẩu owner tại chỗ).

Không in mật khẩu/ticket/cookie. Chỉ in trạng thái + metadata chat.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime

import httpx

COWORK = "https://cowork.vipgroup.com.vn"
BRAIN = "https://ai.vipgroup.com.vn"
OWNER_PW = os.environ.get("COWORK_OWNER_PASSWORD", "")
TAG = datetime.now().strftime("%H%M%S")


def csrf(html: str) -> str:
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html or "")
    if not m:
        raise RuntimeError("Không thấy CSRF")
    return m.group(1)


def client() -> httpx.Client:
    return httpx.Client(follow_redirects=False, timeout=120,
                        headers={"User-Agent": "COWORK-production-smoke/1.0"})


def login(c: httpx.Client, user_id: str, pw: str) -> None:
    r = c.get(COWORK + "/dang-nhap")
    r.raise_for_status()
    r = c.post(COWORK + "/dang-nhap", data={
        "userId": user_id, "matKhau": pw, "_csrf": csrf(r.text), "next": "/"})
    if r.status_code != 303:
        raise RuntimeError(f"login {user_id} → {r.status_code}: {r.text[:200]}")


def main() -> int:
    if not OWNER_PW:
        raise SystemExit("Thiếu COWORK_OWNER_PASSWORD")
    out = {"tag": TAG, "steps": {}}
    owner = client()
    login(owner, "anh-thanh", OWNER_PW)
    out["steps"]["owner_login"] = 303

    emp_id = f"prod-qa-{TAG}"
    emp_pw = "Qa!" + secrets.token_urlsafe(12)
    page = owner.get(COWORK + "/tai-khoan/tao-moi")
    r = owner.post(COWORK + "/tai-khoan/tao-moi", data={
        "_csrf": csrf(page.text), "id": emp_id, "display_name": "QA Production",
        "role_code": "employee", "department_id": "kinh-doanh",
        "password": emp_pw,
    })
    if r.status_code != 200 or "Đã tạo tài khoản" not in r.text:
        raise RuntimeError(f"create employee → {r.status_code}: {r.text[:300]}")
    out["steps"]["create_employee"] = 200
    out["employee"] = emp_id

    emp = client()
    login(emp, emp_id, emp_pw)
    me = emp.get(COWORK + "/api/me").json()["data"]
    out["steps"]["employee_login"] = 303
    out["modules"] = me["modules"]
    assert me["modules"] == ["dashboard", "brain", "tasks", "knowledge", "usage"], me["modules"]

    brain_page = emp.get(COWORK + "/brain")
    assert brain_page.status_code == 200
    launch = emp.post(COWORK + "/brain/mo", data={"_csrf": csrf(brain_page.text)})
    if launch.status_code != 303:
        raise RuntimeError(f"brain/mo → {launch.status_code}: {launch.text[:200]}")
    loc = launch.headers.get("location", "")
    assert loc.startswith(BRAIN + "/cowork/vao?ticket="), loc[:120]
    vao = emp.get(loc)
    if vao.status_code != 303:
        raise RuntimeError(f"brain/vao → {vao.status_code}: {vao.text[:300]}")
    toi = emp.get(BRAIN + "/api/auth/toi")
    if toi.status_code != 200:
        raise RuntimeError(f"brain/toi → {toi.status_code}: {toi.text[:300]}")
    out["steps"]["brain_sso"] = 303
    out["brain_user"] = toi.json()["data"]["userId"]

    prompt = ("Xin chào VIP AI Brain. Hãy xác nhận mô hình AI Local đang xử lý yêu cầu này "
              "và cho tôi biết những chức năng hiện có thể sử dụng.")
    chat = emp.post(BRAIN + "/api/chat", json={"prompt": prompt, "modelId": "auto",
                                              "duAnId": "tong-hop"})
    if chat.status_code != 200:
        raise RuntimeError(f"chat → {chat.status_code}: {chat.text[:300]}")
    d = chat.json().get("data") or {}
    meta = d.get("metadata") or d.get("meta") or {}
    out["steps"]["chat"] = 200
    out["chat"] = {"providerId": d.get("providerId"), "nhan": d.get("nhan"),
                   "model": meta.get("model") or meta.get("moHinh"),
                   "chiPhi": meta.get("chiPhi"), "taskId": d.get("taskId"),
                   "doDaiTraLoi": len(d.get("traLoi") or "")}
    assert d.get("providerId") == "local" and d.get("nhan") == "real", out["chat"]
    assert (d.get("traLoi") or "").strip(), "traLoi rỗng"

    # MFA guard cho owner
    op = owner.get(COWORK + "/brain")
    launch_owner = owner.post(COWORK + "/brain/mo", data={"_csrf": csrf(op.text)})
    if launch_owner.status_code == 303:
        gov = owner.get(launch_owner.headers["location"])
        out["steps"]["owner_mfa_guard"] = gov.status_code
        assert gov.status_code == 403
    else:
        out["steps"]["owner_mfa_guard"] = launch_owner.status_code

    # Thu hồi quyền brain
    pp = owner.get(COWORK + f"/tai-khoan/{emp_id}/phan-quyen")
    rv = owner.post(COWORK + f"/tai-khoan/{emp_id}/phan-quyen", data={
        "_csrf": csrf(pp.text), "quyen_brain": "block"})
    out["steps"]["revoke"] = rv.status_code
    assert emp.get(COWORK + "/brain").status_code == 403
    assert emp.get(BRAIN + "/api/auth/toi").status_code == 401
    out["steps"]["revoke_verified"] = {"cowork": 403, "brain_toi": 401}

    # Trả quyền
    pp2 = owner.get(COWORK + f"/tai-khoan/{emp_id}/phan-quyen")
    rs = owner.post(COWORK + f"/tai-khoan/{emp_id}/phan-quyen", data={
        "_csrf": csrf(pp2.text), "quyen_brain": "default"})
    assert rs.status_code == 303
    assert emp.get(COWORK + "/brain").status_code == 200
    out["steps"]["restore"] = 303

    # Lưu trữ tài khoản QA
    detail = owner.get(COWORK + f"/tai-khoan/{emp_id}")
    arch = owner.post(COWORK + f"/tai-khoan/{emp_id}/luu-tru",
                      data={"_csrf": csrf(detail.text)})
    out["steps"]["archive"] = arch.status_code
    assert arch.status_code == 303
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
