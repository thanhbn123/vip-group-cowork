#!/usr/bin/env python3
"""AG-05 — kịch bản NGHIỆM THU THẬT cho VIP GROUP COWORK (8 bước + kiểm thử bảo mật).

 Nguyên tắc:
 - Chỉ HTTP thật tới dịch vụ đang chạy (COWORK 127.0.0.1:8899, Brain staging 127.0.0.1:8892).
 - Mỗi người một cookie jar riêng (httpx.Client riêng) — không dùng chung phiên.
 - KHÔNG in / KHÔNG ghi mật khẩu, ticket, CSRF, cookie vào log hay bằng chứng.
 - Brain staging chưa sống ⇒ B6–B8 = BLOCKED kèm lý do; không bao giờ fake PASS.
 - Không mock: B7 chỉ PASS khi `nhan == "real"` và `providerId == "local"`.
 - Không chạm Brain production 8891 (chặn cứng nếu cấu hình trỏ vào đó).

 Cách chạy:
    .venv/bin/python scripts/acceptance.py
    .venv/bin/python scripts/acceptance.py --brain-url http://127.0.0.1:8892 --no-cleanup
 Kết quả:
    evidence/AG05-acceptance.json, evidence/AG05-report.md, evidence/AG05-run.log
 Mã thoát:
    0 = tất cả PASS · 1 = có FAIL · 2 = COWORK không sẵn sàng · 3 = có BLOCKED (không FAIL)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.stderr.write("Thiếu httpx — chạy bằng .venv/bin/python scripts/acceptance.py\n")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
JSON_PATH = EVIDENCE / "AG05-acceptance.json"
MD_PATH = EVIDENCE / "AG05-report.md"
LOG_PATH = EVIDENCE / "AG05-run.log"

PROMPT_B7 = (
    "Xin chào VIP AI Brain. Hãy xác nhận mô hình AI Local đang xử lý yêu cầu này "
    "và cho tôi biết những chức năng hiện có thể sử dụng."
)
ADMIN_ROUTES = ["/tai-khoan", "/ban", "/vai-tro", "/nhat-ky", "/cai-dat"]
ADMIN_ROUTES_EXTRA = ["/phan-quyen", "/module-registry"]

# Mật khẩu test cố định của tenant B — lấy từ docs/AGENT-CONTRACTS.md (DB local, không production).
TENANT_B_ID = "b-admin"
TENANT_B_PASSWORD = os.environ.get("AG05_TENANT_B_PASSWORD", "Badmin!Passw0rd")


# --------------------------------------------------------------------------- tiện ích
def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def redact(text: str) -> str:
    """Che ticket/CSRF/mật khẩu nếu lỡ nằm trong URL hoặc chuỗi."""
    text = re.sub(r"(ticket=)[^&\"'\s]+", r"\1***", text or "")
    text = re.sub(r"(_csrf=)[^&\"'\s]+", r"\1***", text)
    text = re.sub(r"(_csrf\"\s+value=\")[^\"]+", r"\1***", text)
    return text


def csrf_tu(html: str) -> str | None:
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html or "")
    return m.group(1) if m else None


def mat_khau_manh() -> str:
    """Sinh mật khẩu mạnh trong bộ nhớ; không ghi ra đĩa/log (chỉ dùng cho tài khoản QA)."""
    chu = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*"
    return "Qa" + "".join(secrets.choice(chu) for _ in range(18)) + "7!"


class LoiNghiemThu(AssertionError):
    pass


# --------------------------------------------------------------------------- lớp chính
class Acceptance:
    def __init__(self, base_url: str, brain_url: str, run_tag: str, cleanup: bool):
        self.base = base_url.rstrip("/")
        self.brain = brain_url.rstrip("/")
        self.run_tag = run_tag
        self.do_cleanup = cleanup
        self.steps: list[dict] = []
        self.security: list[dict] = []
        self.trace: dict[str, list[dict]] = {}
        self.notes: list[str] = []
        self.created: dict[str, str] = {}
        self.passwords: dict[str, str] = {}
        self.brain_ok = False
        self.brain_health: dict = {}
        self.env: dict = {}
        self.started = now_iso()
        self.db_path = Path(os.environ.get("COWORK_DB_PATH") or ROOT / "data" / "cowork.db")
        EVIDENCE.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- log
    def log(self, line: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        safe = redact(line)
        print(f"[{stamp}] {safe}", flush=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{now_iso()} {safe}\n")

    # ---------------------------------------------------------------- db
    def db(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    def db_one(self, sql: str, params: tuple = ()) -> dict | None:
        con = self.db()
        try:
            row = con.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            con.close()

    def db_all(self, sql: str, params: tuple = ()) -> list[dict]:
        con = self.db()
        try:
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()

    # ---------------------------------------------------------------- http
    def new_client(self, label: str) -> httpx.Client:
        client = httpx.Client(
            timeout=httpx.Timeout(180.0, connect=5.0),
            follow_redirects=False,
            headers={"User-Agent": "AG-05-Acceptance/1.0", "Accept": "text/html,application/json"},
        )

        def _hook(request: httpx.Request) -> None:
            self.trace.setdefault(label, []).append({
                "method": request.method,
                "host": request.url.host,
                "port": request.url.port,
                "path": request.url.path,
            })

        client.event_hooks["request"].append(_hook)
        return client

    def call(self, step: dict, client: httpx.Client, method: str, url: str, *,
             label: str = "", **kw) -> httpx.Response:
        """Gọi HTTP thật, ghi lại mã trạng thái (URL đã che ticket)."""
        full = url if url.startswith("http") else self.base + url
        try:
            resp = client.request(method, full, **kw)
        except httpx.HTTPError as exc:
            step["http"].append({"method": method, "url": self._hien(url), "error": type(exc).__name__})
            raise LoiNghiemThu(f"Không gọi được {method} {self._hien(url)}: {type(exc).__name__}") from exc
        step["http"].append({"method": method, "url": self._hien(url), "status": resp.status_code})
        self.log(f"    {method} {self._hien(url)} → {resp.status_code}")
        return resp

    def _hien(self, url: str) -> str:
        if url.startswith(self.base):
            url = url[len(self.base):] or "/"
        elif url.startswith(self.brain):
            url = self.brain + url[len(self.brain):]
        return redact(url)

    def require(self, ok: bool, message: str) -> None:
        if not ok:
            raise LoiNghiemThu(message)

    # ---------------------------------------------------------------- khung bước
    def run_step(self, bucket: list[dict], sid: str, name: str, fn: Callable[[dict], None]) -> dict:
        step = {"id": sid, "name": name, "status": "PENDING", "startedAt": now_iso(),
                "finishedAt": None, "http": [], "details": {}}
        self.log(f"[{sid}] {name}")
        try:
            fn(step)
            if step["status"] == "PENDING":
                step["status"] = "PASS"
        except LoiNghiemThu as exc:
            step["status"] = "FAIL"
            step["details"]["lyDo"] = redact(str(exc))[:500]
        except Exception as exc:  # noqa: BLE001 — mọi lỗi bất ngờ phải thành FAIL, không sập im
            step["status"] = "FAIL"
            step["details"]["lyDo"] = redact(f"{type(exc).__name__}: {exc}")[:500]
            step["details"]["traceback"] = redact(traceback.format_exc())[-1500:]
        step["finishedAt"] = now_iso()
        self.log(f"[{sid}] → {step['status']}" + (
            f" · {step['details'].get('lyDo', '')}" if step["status"] != "PASS" else ""))
        bucket.append(step)
        return step

    def blocked(self, sid: str, name: str, reason: str) -> dict:
        step = {"id": sid, "name": name, "status": "BLOCKED", "startedAt": now_iso(),
                "finishedAt": now_iso(), "http": [],
                "details": {"lyDo": reason, "daKiemTra": self.brain_health}}
        self.steps.append(step)
        self.log(f"[{sid}] → BLOCKED · {reason}")
        return step

    # ---------------------------------------------------------------- phiên
    def dang_nhap(self, step: dict, client: httpx.Client, user_id: str, mat_khau: str,
                  nhan: str) -> None:
        r = self.call(step, client, "GET", "/dang-nhap")
        self.require(r.status_code == 200, f"{nhan}: GET /dang-nhap trả {r.status_code}")
        token = csrf_tu(r.text)
        self.require(bool(token), f"{nhan}: không thấy CSRF trong form đăng nhập")
        r = self.call(step, client, "POST", "/dang-nhap", data={
            "userId": user_id, "matKhau": mat_khau, "_csrf": token, "next": "/"})
        self.require(r.status_code == 303, f"{nhan}: đăng nhập trả {r.status_code} (mong 303)")
        me = self.call(step, client, "GET", "/api/me")
        self.require(me.status_code == 200, f"{nhan}: /api/me trả {me.status_code}")
        data = me.json().get("data") or {}
        self.require(data.get("id") == user_id,
                     f"{nhan}: /api/me trả id khác ({data.get('id')!r})")

    def csrf_cua(self, step: dict, client: httpx.Client, path: str = "/ho-so") -> str:
        r = self.call(step, client, "GET", path)
        self.require(r.status_code == 200, f"GET {path} trả {r.status_code} khi lấy CSRF")
        token = csrf_tu(r.text)
        self.require(bool(token), f"Không thấy CSRF tại {path}")
        return token

    # ---------------------------------------------------------------- khởi động
    def kiem_tra_cowork(self) -> bool:
        try:
            r = httpx.get(self.base + "/api/health", timeout=5.0)
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            self.env["coworkHealth"] = {"loi": f"{type(exc).__name__}: {exc}"[:200]}
            return False
        self.env["coworkHealth"] = {"http": r.status_code, "data": data.get("data")}
        return r.status_code == 200 and (data.get("data") or {}).get("db") == "ok"

    def kiem_tra_brain(self) -> bool:
        if ":8891" in self.brain or "ai.vipgroup.com.vn" in self.brain:
            self.brain_health = {"loi": "CẤM: đích trỏ Brain production — kịch bản dừng."}
            self.log("!! CẤM chạy nghiệm thu vào Brain production 8891 — dừng.")
            return False
        try:
            r = httpx.get(self.brain + "/api/health", timeout=5.0)
        except httpx.HTTPError as exc:
            self.brain_health = {"http": None, "loi": f"{type(exc).__name__}: {str(exc)[:160]}"}
            return False
        try:
            data = r.json()
        except ValueError:
            self.brain_health = {"http": r.status_code, "loi": "Body không phải JSON"}
            return False
        self.brain_health = {"http": r.status_code, "data": data.get("data"),
                             "ok": bool(data.get("ok"))}
        return r.status_code == 200 and (data.get("data") or {}).get("db") == "ok"

    def nguoi_dung_brain(self) -> dict:
        """Thông tin Brain từ chính nó (phienBan/gio) — không lộ bí mật."""
        return (self.brain_health.get("data") or {})

    # ---------------------------------------------------------------- B1
    def buoc_1(self, step: dict) -> None:
        secret_file = ROOT / "secrets" / "owner-anh-thanh.txt"
        self.require(secret_file.is_file(), f"Thiếu tệp mật khẩu chủ sở hữu: {secret_file}")
        owner_pw = secret_file.read_text(encoding="utf-8").strip()
        self.require(bool(owner_pw), "Tệp mật khẩu chủ sở hữu rỗng")
        self.owner = self.new_client("owner")
        r = self.call(step, self.owner, "GET", "/dang-nhap")
        self.require(r.status_code == 200, f"GET /dang-nhap trả {r.status_code}")
        token = csrf_tu(r.text)
        self.require(bool(token), "Trang đăng nhập không có CSRF")
        r = self.call(step, self.owner, "POST", "/dang-nhap", data={
            "userId": "anh-thanh", "matKhau": owner_pw, "_csrf": token, "next": "/"})
        self.require(r.status_code == 303, f"Đăng nhập chủ sở hữu trả {r.status_code} (mong 303)")
        set_cookie = r.headers.get("set-cookie", "")
        thuong = set_cookie.lower()
        self.require("cowork_session=" in set_cookie, "Không thấy cookie phiên sau đăng nhập")
        self.require("httponly" in thuong and "samesite=lax" in thuong,
                     "Cookie phiên thiếu HttpOnly/SameSite=Lax")
        cookie_dau = self.owner.cookies.get("cowork_session")
        self.require(bool(cookie_dau), "Cookie jar không giữ phiên COWORK")
        me = self.call(step, self.owner, "GET", "/api/me")
        self.require(me.status_code == 200, f"/api/me trả {me.status_code}")
        data = me.json().get("data") or {}
        self.require(data.get("id") == "anh-thanh", f"/api/me trả id {data.get('id')!r}")
        self.require(data.get("vaiTro") == "super_admin", f"Vai trò {data.get('vaiTro')!r} ≠ super_admin")
        self.owner_ok = True
        step["details"] = {
            "nguoiDung": data.get("id"), "vaiTro": data.get("vaiTro"),
            "tenantId": data.get("tenantId"), "soModule": len(data.get("modules") or []),
            "cookie": {"ten": "cowork_session", "httpOnly": True, "sameSite": "lax",
                       "giaTri": "***"},
            "matKhauNguon": "secrets/owner-anh-thanh.txt",
        }

    # ---------------------------------------------------------------- B2
    def _tao_tai_khoan(self, step: dict, client: httpx.Client, du_lieu: dict,
                       nhan: str) -> httpx.Response:
        r = self.call(step, client, "GET", "/tai-khoan/tao-moi")
        self.require(r.status_code == 200, f"{nhan}: GET /tai-khoan/tao-moi trả {r.status_code}")
        token = csrf_tu(r.text)
        self.require(bool(token), f"{nhan}: form tạo tài khoản không có CSRF")
        form = {"_csrf": token, **du_lieu}
        return self.call(step, client, "POST", "/tai-khoan/tao-moi", data=form)

    def buoc_2(self, step: dict) -> None:
        self.admin_id = self._id_trong("qa-admin")
        self.passwords[self.admin_id] = mat_khau_manh()
        r = self._tao_tai_khoan(step, self.owner, {
            "id": self.admin_id, "display_name": f"QA Quản trị {self.run_tag}",
            "email": f"{self.admin_id}@qa.local", "role_code": "admin",
            "department_id": "ban-dieu-hanh", "scope_mode": "tenant",
            "password": self.passwords[self.admin_id], "must_change": "0",
        }, "chủ sở hữu")
        self.require(r.status_code == 200, f"Tạo quản trị trả {r.status_code} (mong 200)")
        self.require(self.admin_id in r.text, "Trang kết quả không nhắc ID vừa tạo")
        self.require("Đã tạo tài khoản" in r.text, "Trang kết quả không xác nhận đã tạo tài khoản")
        self.require(self.passwords[self.admin_id] not in r.text,
                     "Mật khẩu QA bị lộ trong HTML kết quả")
        row = self.db_one("SELECT id,tenant_id,role_code,department_id,status FROM users WHERE id=?",
                          (self.admin_id,))
        self.require(row is not None, "DB: không thấy tài khoản quản trị vừa tạo")
        self.require(row["role_code"] == "admin" and row["tenant_id"] == "vip-group",
                     f"DB: vai trò/tenant sai ({row['role_code']}, {row['tenant_id']})")
        self.require(row["status"] == "active", f"DB: trạng thái {row['status']!r} ≠ active")
        scope = self.db_one("SELECT department_id FROM admin_scopes WHERE user_id=?",
                            (self.admin_id,))
        self.require(scope is not None, "DB: thiếu dòng admin_scopes cho quản trị mới")
        self.require(scope["department_id"] is None,
                     "DB: phạm vi quản trị không phải toàn tenant (department_id khác NULL)")
        chi_tiet = self.call(step, self.owner, "GET", f"/tai-khoan/{self.admin_id}")
        self.require(chi_tiet.status_code == 200, f"HTTP chi tiết tài khoản trả {chi_tiet.status_code}")
        self.created["admin"] = self.admin_id
        step["details"] = {
            "id": self.admin_id, "vaiTro": row["role_code"], "ban": row["department_id"],
            "trangThai": row["status"], "phamVi": "tenant (admin_scopes.department_id=NULL)",
            "xacMinhDb": True, "xacMinhHttp": chi_tiet.status_code,
            "matKhau": {"giaTri": "***", "doDai": len(self.passwords[self.admin_id]),
                        "luuO": "bộ nhớ tiến trình, không ghi đĩa"},
        }

    # ---------------------------------------------------------------- B3
    def buoc_3(self, step: dict) -> None:
        self.admin = self.new_client("admin")
        self.dang_nhap(step, self.admin, self.admin_id, self.passwords[self.admin_id], "quản trị QA")
        me = self.call(step, self.admin, "GET", "/api/me")
        data = me.json().get("data") or {}
        self.require(data.get("vaiTro") == "admin", f"Quản trị QA có vai trò {data.get('vaiTro')!r}")

        self.emp_id = self._id_trong("qa-emp")
        self.passwords[self.emp_id] = mat_khau_manh()
        r = self._tao_tai_khoan(step, self.admin, {
            "id": self.emp_id, "display_name": f"QA Nhân viên {self.run_tag}",
            "email": f"{self.emp_id}@qa.local", "role_code": "employee",
            "department_id": "kinh-doanh",
            "password": self.passwords[self.emp_id], "must_change": "0",
        }, "quản trị QA")
        self.require(r.status_code == 200, f"Tạo nhân viên trả {r.status_code} (mong 200)")
        self.require(self.emp_id in r.text, "Trang kết quả không nhắc ID nhân viên vừa tạo")
        self.require(self.passwords[self.emp_id] not in r.text,
                     "Mật khẩu nhân viên QA bị lộ trong HTML kết quả")
        row = self.db_one("SELECT id,tenant_id,role_code,department_id,status,created_by "
                          "FROM users WHERE id=?", (self.emp_id,))
        self.require(row is not None, "DB: không thấy nhân viên vừa tạo")
        self.require(row["role_code"] == "employee", f"DB: vai trò {row['role_code']!r} ≠ employee")
        self.require(row["department_id"] == "kinh-doanh",
                     f"DB: ban {row['department_id']!r} ≠ kinh-doanh")
        self.require(row["created_by"] == self.admin_id,
                     f"DB: người tạo {row['created_by']!r} ≠ quản trị QA")
        chi_tiet = self.call(step, self.admin, "GET", f"/tai-khoan/{self.emp_id}")
        self.require(chi_tiet.status_code == 200, f"Quản trị QA xem chi tiết trả {chi_tiet.status_code}")
        self.created["employee"] = self.emp_id
        self.admin_ok = True
        step["details"] = {
            "id": self.emp_id, "vaiTro": row["role_code"], "ban": row["department_id"],
            "nguoiTao": row["created_by"], "trangThai": row["status"],
            "xacMinhDb": True, "xacMinhHttp": chi_tiet.status_code,
            "matKhau": {"giaTri": "***", "doDai": len(self.passwords[self.emp_id])},
        }

    # ---------------------------------------------------------------- B4
    def buoc_4(self, step: dict) -> None:
        self.emp = self.new_client("employee")
        self.dang_nhap(step, self.emp, self.emp_id, self.passwords[self.emp_id], "nhân viên QA")
        me = self.call(step, self.emp, "GET", "/api/me")
        data = me.json().get("data") or {}
        self.emp_me = data
        self.require(data.get("id") == self.emp_id, "Phiên nhân viên không đúng ID")
        self.require(data.get("tenantId") == "vip-group", "Sai tenant")
        self.require(bool(data.get("modules")), "/api/me không trả module nào")
        self.emp_ok = True
        step["details"] = {"nguoiDung": data.get("id"), "vaiTro": data.get("vaiTro"),
                           "ban": data.get("ban"), "modules": data.get("modules"),
                           "soPhienMoi": 1}

    # ---------------------------------------------------------------- B5
    def buoc_5(self, step: dict) -> None:
        data = self.emp_me
        modules = list(data.get("modules") or [])
        dashboard = self.call(step, self.emp, "GET", "/")
        self.require(dashboard.status_code == 200, f"GET / trả {dashboard.status_code}")
        hrefs = {redact(h) for h in re.findall(r'class="nav-item[^"]*"\s+href="([^"]+)"',
                                               dashboard.text)}
        rows = self.db_all("SELECT code,route FROM modules WHERE status='active'") if modules else []
        routes = {r["code"]: r["route"] for r in rows}
        thieu = [c for c in modules if c not in routes]
        self.require(not thieu, f"DB thiếu module {thieu}")
        mong = {routes[c] for c in modules}
        self.require(hrefs == mong,
                     f"Sidebar lệch /api/me — thừa {sorted(hrefs - mong)}, thiếu {sorted(mong - hrefs)}")
        admin_hrefs = set(ADMIN_ROUTES) | set(ADMIN_ROUTES_EXTRA)
        self.require(not (hrefs & admin_hrefs),
                     f"Sidebar nhân viên chứa mục quản trị {sorted(hrefs & admin_hrefs)}")
        for route in modules:
            if routes[route].startswith("/module/"):
                r = self.call(step, self.emp, "GET", routes[route])
                self.require(r.status_code == 200,
                             f"Module được cấp {routes[route]} trả {r.status_code}")
        b403 = {}
        for route in ADMIN_ROUTES + ADMIN_ROUTES_EXTRA:
            r = self.call(step, self.emp, "GET", route)
            b403[route] = r.status_code
            self.require(r.status_code == 403, f"{route} trả {r.status_code} (mong 403)")
        step["details"] = {
            "apiMeModules": modules, "sidebarHrefs": sorted(hrefs),
            "khopSidebar": True, "soMucQuanTriTrongSidebar": 0,
            "routeQuanTriBiChan": b403,
            "modulesTruyCapDuoc": [routes[c] for c in modules],
        }

    # ---------------------------------------------------------------- B6
    def buoc_6(self, step: dict) -> None:
        if not self.brain_ok:
            step["status"] = "BLOCKED"
            step["details"] = {"lyDo": "Brain staging chưa sẵn sàng — không chạy B6.",
                               "daKiemTra": self.brain_health}
            return
        r = self.call(step, self.emp, "GET", "/brain")
        self.require(r.status_code == 200, f"Nhân viên mở /brain trả {r.status_code}")
        token = csrf_tu(r.text)
        self.require(bool(token), "Trang /brain không có CSRF")
        r = self.call(step, self.emp, "POST", "/brain/mo", data={"_csrf": token})
        self.require(r.status_code == 303, f"POST /brain/mo trả {r.status_code} (mong 303)")
        location = r.headers.get("location", "")
        self.require("/cowork/vao?ticket=" in location,
                     "COWORK không chuyển sang /cowork/vao kèm ticket (Brain báo lỗi?)")
        self.require(":8891" not in location and "ai.vipgroup.com.vn" not in location,
                     "CẢNH BÁO: ticket chuyển tới Brain production — từ chối kiểm thử")
        dich = urlsplit(location)
        mong = urlsplit(self.brain)
        self.require((dich.port or 80) == (mong.port or 80)
                     and (dich.hostname or "") in (mong.hostname or "", "localhost"),
                     f"Đích chuyển hướng không phải Brain staging ({self.brain})")
        ticket_url = redact(location)
        r = self.call(step, self.emp, "GET", location)
        self.require(r.status_code == 303, f"Bridge /cowork/vao trả {r.status_code} (mong 303)")
        self.require(bool(self.emp.cookies.get("vip_session")), "Bridge không đặt cookie phiên Brain")
        toi = self.call(step, self.emp, "GET", self.brain + "/api/auth/toi")
        self.require(toi.status_code == 200, f"Brain /api/auth/toi trả {toi.status_code}")
        body = toi.json()
        self.require(bool(body.get("ok")), "Brain /api/auth/toi trả ok=false")
        brain_user = (body.get("data") or {}).get("userId")
        self.require(brain_user == self.emp_id,
                     f"Brain xác thực sai người: {brain_user!r} ≠ {self.emp_id!r}")
        calls = [c for c in self.trace.get("employee", [])
                 if c["port"] == self._port(self.brain)]
        login_calls = [c for c in calls if "dang-nhap" in c["path"].lower()]
        self.require(not login_calls,
                     f"Có {len(login_calls)} lần đăng nhập thứ hai trên Brain — phải là 0")
        replay = self.new_client("replay")
        rr = self.call(step, replay, "GET", location)
        self.require(rr.status_code == 401,
                     f"Dùng lại ticket cũ trả {rr.status_code} (mong 401 — one-time)")
        step["details"] = {
            "coworkPage": 200, "postMoBrain": 303,
            "redirect": ticket_url, "bridgeVao": 303,
            "brainToi": {"http": toi.status_code, "userId": brain_user,
                         "vaiTro": (body.get("data") or {}).get("vaiTro"),
                         "tenantId": (body.get("data") or {}).get("tenantId")},
            "dangNhapLanHai": 0,
            "goiBrainTrongPhien": len(calls),
            "ticketDungMotLan": {"http": rr.status_code, "ketLuan": "không tái sử dụng được"},
            "cookiePhienBrain": {"ten": "vip_session", "giaTri": "***"},
        }

    # ---------------------------------------------------------------- B7
    def buoc_7(self, step: dict) -> None:
        if not self.brain_ok:
            step["status"] = "BLOCKED"
            step["details"] = {"lyDo": "Brain staging chưa sẵn sàng — không chạy B7.",
                               "daKiemTra": self.brain_health}
            return
        payload = {"prompt": PROMPT_B7, "modelId": "local", "duAnId": "tong-hop"}
        r = self.call(step, self.emp, "POST", self.brain + "/api/chat", json=payload)
        step["details"]["prompt"] = PROMPT_B7
        self.require(r.status_code == 200, f"Brain /api/chat trả {r.status_code}")
        try:
            body = r.json()
        except ValueError:
            raise LoiNghiemThu("Brain /api/chat trả body không phải JSON")
        if not body.get("ok"):
            loi = body.get("loi") or {}
            step["details"]["loiBrain"] = {"ma": loi.get("ma"), "thongBao": loi.get("thongBao")}
            raise LoiNghiemThu(
                f"Brain từ chối chat ({loi.get('ma')}): {loi.get('thongBao')}")
        data = body.get("data") or {}
        tra_loi = (data.get("traLoi") or "").strip()
        nhan = data.get("nhan")
        provider = data.get("providerId")
        meta = data.get("meta") or {}
        router = data.get("router") or {}
        step["details"].update({
            "providerId": provider, "nhan": nhan,
            "meta": {k: meta.get(k) for k in ("provider", "model", "doTreMs", "tokenVao",
                                              "tokenRa", "chiPhi", "giaCo")},
            "router": {k: router.get(k) for k in ("provider", "luat", "lyDo")},
            "taskId": data.get("taskId"),
            "doDaiTraLoi": len(tra_loi),
            "traLoiTrich": tra_loi[:400],
            "biChan": data.get("biChan"),
        })
        self.require(provider == "local",
                     f"providerId={provider!r} — không phải 'local' (từ chối cloud/mock)")
        self.require(nhan == "real",
                     f"nhan={nhan!r} — KHÔNG phải lời gọi thật (mock/cloud bị từ chối)")
        self.require(bool(tra_loi), "traLoi rỗng")
        self.require(len(tra_loi) >= 20, f"traLoi quá ngắn ({len(tra_loi)} ký tự)")
        self.require(meta.get("model"), "meta.model rỗng — không xác định được mô hình")

    # ---------------------------------------------------------------- B8
    def buoc_8(self, step: dict) -> None:
        if not self.brain_ok:
            step["status"] = "BLOCKED"
            step["details"] = {"lyDo": "Brain staging chưa sẵn sàng — không chạy B8.",
                               "daKiemTra": self.brain_health}
            return
        token = self.csrf_cua(step, self.owner, "/ho-so")
        thoi_diem = now_iso()
        r = self.call(step, self.owner, "POST", f"/tai-khoan/{self.emp_id}/phan-quyen",
                      data={"_csrf": token, "quyen_brain": "block"})
        self.require(r.status_code == 303, f"Thu hồi quyền Brain trả {r.status_code} (mong 303)")
        perms = self.db_all("SELECT permission_code,effect FROM user_permissions "
                            "WHERE user_id=? AND permission_code IN ('brain.view','brain.use')",
                            (self.emp_id,))
        self.require({p["permission_code"] for p in perms} == {"brain.view", "brain.use"},
                     f"DB: thiếu bản ghi thu hồi brain ({perms})")
        self.require(all(p["effect"] == "deny" for p in perms),
                     "DB: bản ghi thu hồi không phải deny")
        cowork_brain = self.call(step, self.emp, "GET", "/brain")
        self.require(cowork_brain.status_code == 403,
                     f"COWORK /brain sau thu hồi trả {cowork_brain.status_code} (mong 403)")
        mo_lai = self.call(step, self.emp, "POST", "/brain/mo",
                           data={"_csrf": self.csrf_cua(step, self.emp, "/ho-so")})
        self.require(mo_lai.status_code == 403,
                     f"POST /brain/mo sau thu hồi trả {mo_lai.status_code} (mong 403)")
        toi = self.call(step, self.emp, "GET", self.brain + "/api/auth/toi")
        self.require(toi.status_code == 401,
                     f"Phiên Brain cũ vẫn dùng được (HTTP {toi.status_code}, mong 401)")
        step["details"] = {
            "thoiDiemThuHoi": thoi_diem,
            "nguoiThucHien": "anh-thanh (super_admin)",
            "hinhThuc": "thu hồi quyền module brain (user_permissions deny)",
            "dbQuyen": [dict(p) for p in perms],
            "coworkBrain": cowork_brain.status_code,
            "coworkBrainMo": mo_lai.status_code,
            "brainToiSauThuHoi": toi.status_code,
            "phienBrainCu": "không truy cập được (401)",
        }

    # ---------------------------------------------------------------- bảo mật
    def s1_khong_cookie(self, step: dict) -> None:
        anon = self.new_client("anon")
        r = self.call(step, anon, "GET", "/")
        self.require(r.status_code == 303, f"GET / không cookie trả {r.status_code} (mong 303)")
        self.require("/dang-nhap" in r.headers.get("location", ""),
                     "GET / không chuyển về /dang-nhap")
        api = self.call(step, anon, "GET", "/api/me")
        self.require(api.status_code == 401, f"/api/me không cookie trả {api.status_code} (mong 401)")
        body = api.json()
        self.require((body.get("loi") or {}).get("ma") == "CHUA_DANG_NHAP",
                     "Mã lỗi /api/me không phải CHUA_DANG_NHAP")
        adm = self.call(step, anon, "GET", "/tai-khoan")
        self.require(adm.status_code == 303, f"/tai-khoan không cookie trả {adm.status_code} (mong 303)")
        step["details"] = {"trangChu": 303, "apiMe": 401, "taiKhoan": 303,
                           "chuyenHuong": redact(r.headers.get("location", ""))}

    def s2_thieu_csrf(self, step: dict) -> None:
        tam_id = f"qa-csrf-{self.run_tag}"
        r = self.call(step, self.owner, "POST", "/tai-khoan/tao-moi", data={
            "id": tam_id, "display_name": "CSRF test", "role_code": "employee",
            "department_id": "kinh-doanh", "password": mat_khau_manh(), "must_change": "0"})
        self.require(r.status_code == 403, f"POST thiếu CSRF trả {r.status_code} (mong 403)")
        self.require(self.db_one("SELECT 1 FROM users WHERE id=?", (tam_id,)) is None,
                     "DB: tài khoản vẫn được tạo dù thiếu CSRF!")
        r2 = self.call(step, self.emp, "POST", "/tai-khoan/tao-moi", data={
            "_csrf": "sai-token", "id": tam_id + "-2", "display_name": "CSRF test",
            "role_code": "employee", "department_id": "kinh-doanh", "password": mat_khau_manh()})
        self.require(r2.status_code == 403, f"POST CSRF sai trả {r2.status_code} (mong 403)")
        token = self.csrf_cua(step, self.emp, "/ho-so")
        r3 = self.call(step, self.emp, "POST", "/ho-so", data={"_csrf": token, "display_name": "X"},
                       headers={"Origin": "https://evil.example"})
        self.require(r3.status_code == 403, f"POST khác Origin trả {r3.status_code} (mong 403)")
        step["details"] = {"thieuCsrf": 403, "csrfSai": 403, "originLa": 403,
                           "taiKhoanKhongDuocTao": True}

    def s3_nhan_vien_goi_quan_tri(self, step: dict) -> None:
        ket_qua = {}
        for route in ADMIN_ROUTES + ADMIN_ROUTES_EXTRA:
            r = self.call(step, self.emp, "GET", route)
            ket_qua[route] = r.status_code
            self.require(r.status_code == 403, f"{route} trả {r.status_code} (mong 403)")
        token = self.csrf_cua(step, self.emp, "/ho-so")
        r = self.call(step, self.emp, "POST", f"/tai-khoan/{self.admin_id}/khoa",
                      data={"_csrf": token})
        # Quy ước COWORK: POST bị từ chối ở tầng nghiệp vụ trả 303 + flash lỗi
        # (xem routers/accounts.py bắt Forbidden). GET route quản trị vẫn phải 403.
        self.require(r.status_code in (403, 303),
                     f"POST khoá tài khoản trả {r.status_code} (mong 403 hoặc 303 kèm flash lỗi)")
        con = self.db()
        try:
            trang_thai = con.execute("SELECT status FROM users WHERE id=?",
                                     (self.admin_id,)).fetchone()[0]
        finally:
            con.close()
        self.require(trang_thai == "active", f"Tài khoản quản trị bị đổi trạng thái ({trang_thai})")
        nhat_ky = self.db_one("SELECT COUNT(*) AS n FROM audit_log "
                              "WHERE action='account.suspend' AND target_id=?", (self.admin_id,))
        self.require((nhat_ky or {}).get("n") == 0,
                     "Audit có ghi account.suspend — thao tác của nhân viên đã có hiệu lực!")
        step["details"] = {
            "routeGet": ket_qua, "postKhoaHttp": r.status_code,
            "postKhoaBiChan": True, "quanTriVanActive": True,
            "auditSuspend": 0,
            "ghiChu": ("GET route quản trị = 403; POST khoá bị chặn ở service, COWORK trả 303 "
                       "+ flash lỗi theo quy ước của routers/accounts.py — trạng thái không đổi."),
        }

    def s4_cross_tenant(self, step: dict) -> None:
        client = self.new_client("tenant-b")
        self.dang_nhap(step, client, TENANT_B_ID, TENANT_B_PASSWORD, "b-admin")
        me = self.call(step, client, "GET", "/api/me")
        data = me.json().get("data") or {}
        self.require(data.get("tenantId") == "tenant-b",
                     f"b-admin có tenant {data.get('tenantId')!r} ≠ tenant-b")
        xem = self.call(step, client, "GET", "/tai-khoan/anh-thanh")
        self.require(xem.status_code == 404, f"b-admin xem anh-thanh trả {xem.status_code} (mong 404)")
        token = self.csrf_cua(step, client, "/ho-so")
        khoa = self.call(step, client, "POST", "/tai-khoan/anh-thanh/khoa", data={"_csrf": token})
        self.require(khoa.status_code == 404, f"b-admin khoá anh-thanh trả {khoa.status_code} (mong 404)")
        danh_sach = self.call(step, client, "GET", "/tai-khoan")
        self.require(danh_sach.status_code == 200, f"b-admin xem danh sách trả {danh_sach.status_code}")
        self.require("anh-thanh" not in danh_sach.text, "Danh sách tenant B lộ anh-thanh")
        row = self.db_one("SELECT status FROM users WHERE id='anh-thanh'")
        self.require(row and row["status"] == "active", "anh-thanh không còn active sau thử nghiệm")
        step["details"] = {"tenantId": data.get("tenantId"), "xemAnhThanh": 404,
                           "khoaAnhThanh": 404, "danhSachKhongLo": True,
                           "anhThanhVanActive": True}

    def s5_phien_bi_thu_hoi(self, step: dict) -> None:
        token = self.csrf_cua(step, self.owner, "/ho-so")
        r = self.call(step, self.owner, "POST", f"/tai-khoan/{self.admin_id}/thu-hoi-phien",
                      data={"_csrf": token})
        self.require(r.status_code == 303, f"Thu hồi phiên trả {r.status_code} (mong 303)")
        home = self.call(step, self.admin, "GET", "/")
        self.require(home.status_code == 303, f"Phiên bị thu hồi vẫn vào / (HTTP {home.status_code})")
        self.require("/dang-nhap" in home.headers.get("location", ""),
                     "Phiên bị thu hồi không chuyển về /dang-nhap")
        api = self.call(step, self.admin, "GET", "/api/me")
        self.require(api.status_code == 401, f"Phiên bị thu hồi /api/me trả {api.status_code}")
        row = self.db_all("SELECT status FROM sessions WHERE user_id=?", (self.admin_id,))
        self.require(row and all(s["status"] != "active" for s in row),
                     "DB: vẫn còn phiên active sau thu hồi")
        step["details"] = {"thuHoi": 303, "trangChuSauThuHoi": 303,
                           "chuyenHuong": redact(home.headers.get("location", "")),
                           "apiMe": 401, "soPhienActiveConLai": 0}

    def s6_brain_cong_bridge(self, step: dict) -> None:
        if not self.brain_ok:
            step["status"] = "BLOCKED"
            step["details"] = {"lyDo": "Brain staging chưa sẵn sàng — không kiểm tra cổng bridge.",
                               "daKiemTra": self.brain_health}
            return
        anon = self.new_client("brain-anon")
        vao = self.call(step, anon, "GET", self.brain + "/cowork/vao")
        self.require(vao.status_code == 400, f"/cowork/vao không ticket trả {vao.status_code} (mong 400)")
        thu_hoi = self.call(step, anon, "POST", self.brain + "/api/cowork/thu-hoi",
                            json={"userId": "anh-thanh"})
        self.require(thu_hoi.status_code == 401,
                     f"/api/cowork/thu-hoi không chữ ký trả {thu_hoi.status_code} (mong 401)")
        step["details"] = {"vaoKhongTicket": 400, "thuHoiKhongChuKy": 401}

    # ---------------------------------------------------------------- dọn dẹp
    def don_dep(self) -> dict:
        ket_qua: dict = {"batDau": now_iso(), "taiKhoan": {}}
        if not self.do_cleanup:
            ket_qua["boQua"] = "--no-cleanup"
            return ket_qua
        if not self.created:
            ket_qua["boQua"] = "không có tài khoản QA nào được tạo"
            return ket_qua
        for vai_tro, uid in self.created.items():
            muc: dict = {"id": uid, "hanhDong": []}
            try:
                token = self.csrf_cua({"http": []}, self.owner, "/ho-so")
                r = self.owner.post(self.base + f"/tai-khoan/{uid}/thu-hoi-phien",
                                    data={"_csrf": token})
                muc["hanhDong"].append({"thuHoiPhien": r.status_code})
                token = self.csrf_cua({"http": []}, self.owner, "/ho-so")
                r = self.owner.post(self.base + f"/tai-khoan/{uid}/luu-tru",
                                    data={"_csrf": token})
                muc["hanhDong"].append({"luuTru": r.status_code})
                row = self.db_one("SELECT status FROM users WHERE id=?", (uid,))
                muc["trangThaiSau"] = row["status"] if row else "khong-thay"
                muc["ketQua"] = ("PASS" if r.status_code == 303 and row
                                 and row["status"] == "archived" else "FAIL")
            except (httpx.HTTPError, LoiNghiemThu) as exc:
                muc["ketQua"] = "FAIL"
                muc["lyDo"] = redact(str(exc))[:200]
            ket_qua["taiKhoan"][vai_tro] = muc
        ket_qua["ketThuc"] = now_iso()
        ket_qua["ghiChu"] = ("Tài khoản QA đã lưu trữ (archived), không xoá cứng; "
                             "bản ghi audit còn nguyên.")
        return ket_qua

    # ---------------------------------------------------------------- tiện ích id
    def _id_trong(self, prefix: str) -> str:
        base = f"{prefix}-{self.run_tag}"
        ung_vien, i = base, 2
        while self.db_one("SELECT 1 FROM users WHERE id=?", (ung_vien,)):
            ung_vien = f"{base}-{i}"
            i += 1
        return ung_vien[:40]

    @staticmethod
    def _port(url: str) -> int:
        m = re.search(r":(\d+)$", url)
        return int(m.group(1)) if m else 80

    # ---------------------------------------------------------------- chạy
    def chay(self) -> int:
        self.log("=" * 78)
        self.log(f"AG-05 nghiệm thu COWORK · tag={self.run_tag} · COWORK={self.base} · Brain={self.brain}")
        cowork_ok = self.kiem_tra_cowork()
        self.env["dbPath"] = str(self.db_path)
        self.env["cowork"] = self.base
        self.env["brain"] = self.brain
        self.env["brainProductionGuard"] = ":8891 bị chặn"
        if not cowork_ok:
            self.log("!! COWORK /api/health không sẵn sàng — không chạy được bước nào.")
            self.env["ketQua"] = "COWORK DOWN"
            self.ghi_bang_chung(None)
            return 2
        self.log(f"COWORK health OK · DB={self.db_path}")
        self.brain_ok = self.kiem_tra_brain()
        self.log(f"Brain staging: {'SẴN SÀNG' if self.brain_ok else 'CHƯA SẴN SÀNG'} · "
                 f"{self.brain_health}")

        self.run_step(self.steps, "B1", "Chủ sở hữu đăng nhập COWORK", self.buoc_1)
        for sid, ten, ham, phu_thuoc in (
            ("B2", "Tạo quản trị cấp dưới mới (qa-admin-*)", self.buoc_2, "B1"),
            ("B3", "Quản trị tạo nhân viên Ban Kinh doanh (qa-emp-*)", self.buoc_3, "B2"),
            ("B4", "Nhân viên đăng nhập", self.buoc_4, "B3"),
            ("B5", "Nhân viên chỉ thấy module được cấp", self.buoc_5, "B4"),
        ):
            if self._step(phu_thuoc)["status"] == "PASS":
                self.run_step(self.steps, sid, ten, ham)
            else:
                self.steps.append({
                    "id": sid, "name": ten, "status": "BLOCKED", "startedAt": now_iso(),
                    "finishedAt": now_iso(), "http": [],
                    "details": {"lyDo": f"Không chạy được vì {phu_thuoc} chưa PASS."}})
                self.log(f"[{sid}] → BLOCKED · phụ thuộc {phu_thuoc}")

        if not self.brain_ok:
            ly_do = ("Brain staging chưa sẵn sàng — GET " + self.brain +
                     "/api/health không đạt. Kiểm tra: " +
                     json.dumps(self.brain_health, ensure_ascii=False))
            self.blocked("B6", "Mở VIP AI Brain từ COWORK (SSO ticket)", ly_do)
            self.blocked("B7", "Chat thật với AI Local (local/real)", "Brain staging chưa sẵn sàng.")
            self.blocked("B8", "Thu hồi quyền Brain + phiên Brain cũ", "Brain staging chưa sẵn sàng.")
        elif self._step("B5")["status"] != "PASS" or not self.created.get("employee"):
            self.blocked("B6", "Mở VIP AI Brain từ COWORK (SSO ticket)",
                         "B1–B5 chưa PASS — chưa có phiên nhân viên QA để mở Brain.")
            self.blocked("B7", "Chat thật với AI Local (local/real)", "Phụ thuộc B6 PASS.")
            self.blocked("B8", "Thu hồi quyền Brain + phiên Brain cũ", "Phụ thuộc B6 PASS.")
        else:
            self.run_step(self.steps, "B6", "Mở VIP AI Brain từ COWORK (SSO ticket)", self.buoc_6)
            if self._step("B6")["status"] == "PASS":
                self.run_step(self.steps, "B7", "Chat thật với AI Local (local/real)", self.buoc_7)
                # B8 kiểm chứng thu hồi trên chính phiên Brain vừa mở ở B6 — không phụ thuộc B7.
                self.run_step(self.steps, "B8", "Thu hồi quyền Brain + phiên Brain cũ", self.buoc_8)
            else:
                self.blocked("B7", "Chat thật với AI Local (local/real)", "Phụ thuộc B6 PASS.")
                self.blocked("B8", "Thu hồi quyền Brain + phiên Brain cũ", "Phụ thuộc B6 PASS.")

        # Kiểm thử bảo mật (chạy được cả khi B6–B8 BLOCKED)
        self.run_step(self.security, "S1", "Không cookie → 303/401", self.s1_khong_cookie)
        if getattr(self, "owner_ok", False) and getattr(self, "emp_ok", False):
            self.run_step(self.security, "S2", "Thiếu/sai CSRF → 403", self.s2_thieu_csrf)
            self.run_step(self.security, "S3", "Nhân viên gọi route quản trị → 403",
                          self.s3_nhan_vien_goi_quan_tri)
        else:
            self.blocked_security("S2", "Thiếu/sai CSRF → 403", "Thiếu phiên chủ sở hữu/nhân viên QA")
            self.blocked_security("S3", "Nhân viên gọi route quản trị → 403",
                                  "Thiếu phiên nhân viên QA")
        self.run_step(self.security, "S4", "Cross-tenant: b-admin không đọc được anh-thanh → 404",
                      self.s4_cross_tenant)
        if getattr(self, "admin_ok", False):
            self.run_step(self.security, "S5", "Phiên bị thu hồi → 303 /dang-nhap",
                          self.s5_phien_bi_thu_hoi)
        else:
            self.blocked_security("S5", "Phiên bị thu hồi → 303 /dang-nhap",
                                  "Thiếu phiên quản trị QA")
        self.run_step(self.security, "S6", "Cổng bridge Brain fail-closed", self.s6_brain_cong_bridge)

        cleanup = self.don_dep()
        return self.ghi_bang_chung(cleanup)

    def blocked_security(self, sid: str, name: str, reason: str) -> None:
        self.security.append({"id": sid, "name": name, "status": "BLOCKED",
                              "startedAt": now_iso(), "finishedAt": now_iso(),
                              "http": [], "details": {"lyDo": reason}})
        self.log(f"[{sid}] → BLOCKED · {reason}")

    def _step(self, sid: str) -> dict:
        for s in self.steps:
            if s["id"] == sid:
                return s
        raise KeyError(sid)

    # ---------------------------------------------------------------- bằng chứng
    def ghi_bang_chung(self, cleanup: dict | None) -> int:
        for s in self.steps:
            s["details"] = json.loads(redact(json.dumps(s["details"], ensure_ascii=False, default=str)))
        for s in self.security:
            s["details"] = json.loads(redact(json.dumps(s["details"], ensure_ascii=False, default=str)))
        dem = {k: sum(1 for s in self.steps if s["status"] == k) for k in ("PASS", "FAIL", "BLOCKED")}
        dem_bm = {k: sum(1 for s in self.security if s["status"] == k)
                  for k in ("PASS", "FAIL", "BLOCKED")}
        tong = {
            "steps": dem, "security": dem_bm,
            "ketLuan": ("PASS toàn bộ" if not dem["FAIL"] and not dem["BLOCKED"]
                        else ("CÓ BLOCKED" if not dem["FAIL"] else "CÓ FAIL")),
        }
        evidence = {
            "meta": {
                "agent": "AG-05 QA & SECURITY", "duAn": "VIP GROUP COWORK",
                "batDau": self.started, "ketThuc": now_iso(), "runTag": self.run_tag,
                "cowork": self.base, "brain": self.brain,
                "brainProductionGuard": "không chạm 127.0.0.1:8891 / ai.vipgroup.com.vn",
                "dbDoc": str(self.db_path), "coworkHealth": self.env.get("coworkHealth"),
                "brainHealth": self.brain_health,
                "phienBanScript": "1.0.0",
                "nguyenTac": ["HTTP thật, cookie jar riêng từng người",
                              "không in mật khẩu/ticket/CSRF",
                              "mock/cloud không được tính PASS"],
                "luuY": [
                    ("POST quản trị bị từ chối ở tầng nghiệp vụ trả 303 + flash lỗi "
                     "(quy ước routers/accounts.py); GET route quản trị trả 403."),
                    ("Brain staging (uvicorn access log) ghi ticket trong query string — "
                     "ticket dùng một lần, TTL 60 giây; nên tắt/che access log khi lên thật."),
                ],
            },
            "buoc": self.steps,
            "kiemThuBaoMat": self.security,
            "donDep": cleanup,
            "tongHop": tong,
        }
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        MD_PATH.write_text(self._bao_cao(evidence), encoding="utf-8")
        self.log(f"Đã ghi {JSON_PATH.name} và {MD_PATH.name}")
        self.log(f"Tổng hợp: {tong}")
        if dem["FAIL"]:
            return 1
        if dem["BLOCKED"]:
            return 3
        return 0

    def _bao_cao(self, ev: dict) -> str:
        meta, tong = ev["meta"], ev["tongHop"]
        nhan = {"PASS": "PASS", "FAIL": "FAIL", "BLOCKED": "BLOCKED"}
        dong = []
        for s in ev["buoc"]:
            ly_do = (s["details"].get("lyDo") or "").replace("|", "\\|")[:220]
            ma = "; ".join(f"{h['method']} {h['url']}={h.get('status', h.get('error', '?'))}"
                           for h in s["http"])[:300]
            dong.append(f"| {s['id']} | {s['name']} | {nhan.get(s['status'], s['status'])} | "
                        f"{ma or '—'} | {ly_do or '—'} |")
        bm = []
        for s in ev["kiemThuBaoMat"]:
            ly_do = (s["details"].get("lyDo") or "").replace("|", "\\|")[:220]
            ma = "; ".join(f"{h['method']} {h['url']}={h.get('status', h.get('error', '?'))}"
                           for h in s["http"])[:300]
            bm.append(f"| {s['id']} | {s['name']} | {nhan.get(s['status'], s['status'])} | "
                      f"{ma or '—'} | {ly_do or '—'} |")
        blocked = [s for s in ev["buoc"] + ev["kiemThuBaoMat"] if s["status"] == "BLOCKED"]
        faill = [s for s in ev["buoc"] + ev["kiemThuBaoMat"] if s["status"] == "FAIL"]
        chi_tiet = []
        for s in ev["buoc"]:
            if s["status"] == "PASS" and s["id"] in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"):
                chi_tiet.append(f"\n### {s['id']} — {s['name']}\n```json\n"
                                + json.dumps(s["details"], ensure_ascii=False, indent=2) + "\n```")
        don = ev.get("donDep") or {}
        return f"""# AG-05 — BÁO CÁO NGHIỆM THU COWORK & BRAIN STAGING

**Thời điểm:** {meta['batDau']} → {meta['ketThuc']}  ·  **Run tag:** `{meta['runTag']}`
**Môi trường:** COWORK `{meta['cowork']}` · Brain `{meta['brain']}` · DB `{meta['dbDoc']}`
**Chế độ:** HTTP thật, mỗi người một cookie jar, không mock, không chạm Brain production 8891.
**Tệp bằng chứng:** `evidence/AG05-acceptance.json` · `evidence/AG05-run.log`

## 1. Tổng hợp

| Hạng mục | PASS | FAIL | BLOCKED |
|---|---|---|---|
| 8 bước nghiệm thu | {tong['steps']['PASS']} | {tong['steps']['FAIL']} | {tong['steps']['BLOCKED']} |
| Kiểm thử bảo mật | {tong['security']['PASS']} | {tong['security']['FAIL']} | {tong['security']['BLOCKED']} |

**Kết luận:** {tong['ketLuan']}

## 2. Tám bước nghiệm thu

| Bước | Nội dung | Kết quả | HTTP | Ghi chú |
|---|---|---|---|---|
{chr(10).join(dong)}

## 3. Kiểm thử bảo mật E2E

| Mã | Nội dung | Kết quả | HTTP | Ghi chú |
|---|---|---|---|---|
{chr(10).join(bm)}

## 4. Phần BLOCKED / FAIL
{(chr(10) + chr(10).join(f"- **{s['id']} {s['name']}** — {s['status']}: {s['details'].get('lyDo', '')}" for s in blocked + faill)) if blocked or faill else chr(10) + "- Không có."}

## 5. Dọn tài khoản QA
```json
{json.dumps(don, ensure_ascii=False, indent=2)}
```

## 6. Ghi chú kỹ thuật
- Brain staging health: `{json.dumps(meta['brainHealth'], ensure_ascii=False)}`
- COWORK health: `{json.dumps(meta['coworkHealth'], ensure_ascii=False)}`
- Mật khẩu QA sinh trong bộ nhớ, không ghi ra đĩa; tài khoản QA được **lưu trữ** (archived), không xoá cứng.
- B7 chỉ PASS khi `providerId=local` **và** `nhan=real`; mọi trường hợp mock/cloud bị đánh FAIL.
- Không sửa mã ứng dụng, template, auth, services, brain hay script khác (đúng vùng sở hữu AG-05).

**Lưu ý an toàn:**
{chr(10).join('- ' + g for g in meta.get('luuY', []))}

## 7. Chi tiết bước PASS
{''.join(chi_tiet) if chi_tiet else '_Không có bước PASS để hiển thị._'}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="AG-05 acceptance cho VIP GROUP COWORK")
    parser.add_argument("--base-url", default=os.environ.get("COWORK_BASE_URL", "http://127.0.0.1:8899"))
    parser.add_argument("--brain-url", default=os.environ.get("COWORK_BRAIN_PUBLIC_URL",
                                                              "http://127.0.0.1:8892"))
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d-%H%M%S"),
                        help="hậu tố ID tài khoản QA (mặc định: thời điểm chạy)")
    parser.add_argument("--no-cleanup", action="store_true",
                        help="giữ tài khoản QA ở trạng thái active để controller kiểm tra")
    args = parser.parse_args()
    if ":8891" in args.brain_url:
        sys.stderr.write("CẤM: --brain-url trỏ Brain production 8891.\n")
        return 2
    tag = re.sub(r"[^0-9a-zA-Z-]", "-", args.tag)[:24]
    app = Acceptance(args.base_url, args.brain_url, tag, not args.no_cleanup)
    try:
        return app.chay()
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
