"""AG-05 — kiểm thử E2E bảo mật (chạy in-process, DB tạm của conftest).

Bổ sung cho `tests/test_cowork.py` (không sửa tệp của làn khác). Mỗi test dùng
TestClient riêng cho từng người để mô phỏng đúng "mỗi người một cookie jar":

  1. Không cookie        → 303 /dang-nhap (trang) và 401 (API).
  2. Thiếu/sai CSRF      → 403, không có bản ghi nào được tạo.
  3. Nhân viên gọi route quản trị → 403; POST bị chặn ở service (303 + flash,
     trạng thái không đổi — quy ước của routers/accounts.py).
  4. Cross-tenant        → b-admin (tenant-b) không đọc/khoá được anh-thanh: 404.
  5. Phiên bị thu hồi    → 303 /dang-nhap, /api/me 401.
  6. Luồng B1–B5        → chủ sở hữu tạo quản trị, quản trị tạo nhân viên,
     nhân viên đăng nhập, chỉ thấy module được cấp.
  7. Brain tắt           → /brain/mo không phát ticket, quay lại /brain.
"""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from conftest import csrf_cua, csrf_tu, dang_nhap, tao_user
from cowork import db, services
from cowork.main import app

ROUTES_QUAN_TRI = ["/tai-khoan", "/ban", "/vai-tro", "/nhat-ky", "/cai-dat",
                   "/phan-quyen", "/module-registry"]


def _client() -> TestClient:
    """TestClient mới = cookie jar riêng (không dùng chung phiên với người khác)."""
    return TestClient(app)


def _sidebar_hrefs(html: str) -> set[str]:
    return set(re.findall(r'class="nav-item[^"]*"\s+href="([^"]+)"', html))


def _tao_qua_http(client: TestClient, du_lieu: dict):
    trang = client.get("/tai-khoan/tao-moi")
    assert trang.status_code == 200, "Phải vào được trang tạo tài khoản"
    token = csrf_tu(trang.text)
    return client.post("/tai-khoan/tao-moi", data={"_csrf": token, **du_lieu})


# ------------------------------------------------------------------ 1. không cookie
def test_e2e_khong_cookie_bi_chuyen_huong_va_api_401():
    with _client() as anon:
        home = anon.get("/", follow_redirects=False)
        assert home.status_code == 303
        assert "/dang-nhap" in home.headers["location"]

        api = anon.get("/api/me")
        assert api.status_code == 401
        assert api.json()["loi"]["ma"] == "CHUA_DANG_NHAP"

        admin = anon.get("/tai-khoan", follow_redirects=False)
        assert admin.status_code == 303
        assert "/dang-nhap" in admin.headers["location"]


# ------------------------------------------------------------------ 2. CSRF
def test_e2e_thieu_hoac_sai_csrf_bi_chan_403(client, owner):
    dang_nhap(client, "anh-thanh", "Owner!Passw0rd")
    r = client.post("/tai-khoan/tao-moi", data={
        "id": "e2e-csrf-01", "display_name": "CSRF thiếu", "role_code": "employee",
        "department_id": "kinh-doanh", "password": "CsrfThieu!123",
    })
    assert r.status_code == 403
    conn = db.connect()
    try:
        assert conn.execute("SELECT 1 FROM users WHERE id='e2e-csrf-01'").fetchone() is None
    finally:
        conn.close()

    r = client.post("/tai-khoan/tao-moi", data={
        "_csrf": "token-sai", "id": "e2e-csrf-02", "display_name": "CSRF sai",
        "role_code": "employee", "department_id": "kinh-doanh", "password": "CsrfSai!1234",
    })
    assert r.status_code == 403
    conn = db.connect()
    try:
        assert conn.execute("SELECT 1 FROM users WHERE id='e2e-csrf-02'").fetchone() is None
    finally:
        conn.close()

    # CSRF đúng nhưng Origin khác host → 403 (chặn CSRF cross-site).
    token = csrf_cua(client)
    r = client.post("/ho-so", data={"_csrf": token, "display_name": "Origin la"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


# ------------------------------------------------------------------ 3. route quản trị
def test_e2e_nhan_vien_goi_route_quan_tri_bi_403(client, owner):
    tao_user("employee", "e2e-emp-01", dept="kinh-doanh")
    with _client() as emp:
        assert dang_nhap(emp, "e2e-emp-01", "User!Passw0rd").status_code == 303
        for route in ROUTES_QUAN_TRI:
            assert emp.get(route).status_code == 403, f"{route} phải 403"

        token = csrf_cua(emp)
        r = emp.post("/tai-khoan/anh-thanh/khoa", data={"_csrf": token},
                     follow_redirects=False)
        # Quy ước COWORK: POST bị từ chối ở service → 303 kèm flash lỗi; GET vẫn 403.
        assert r.status_code in (403, 303)
        conn = db.connect()
        try:
            row = conn.execute("SELECT status FROM users WHERE id='anh-thanh'").fetchone()
            assert row["status"] == "active"
            assert conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action='account.suspend' "
                "AND target_id='anh-thanh'").fetchone()[0] == 0
        finally:
            conn.close()


# ------------------------------------------------------------------ 4. cross-tenant
def test_e2e_cross_tenant_khong_doc_duoc_anh_thanh(client, owner):
    conn = db.connect()
    try:
        services.tao_super_admin(conn, "e2e-b-admin", "Badmin!Passw0rd", "e2e-b-admin",
                                 tenant_id="tenant-b")
    finally:
        conn.close()

    with _client() as b:
        assert dang_nhap(b, "e2e-b-admin", "Badmin!Passw0rd").status_code == 303
        assert b.get("/api/me").json()["data"]["tenantId"] == "tenant-b"
        assert b.get("/tai-khoan/anh-thanh").status_code == 404
        token = csrf_cua(b)
        assert b.post("/tai-khoan/anh-thanh/khoa",
                      data={"_csrf": token}).status_code == 404
        assert "anh-thanh" not in b.get("/tai-khoan").text
        conn = db.connect()
        try:
            assert conn.execute(
                "SELECT status FROM users WHERE id='anh-thanh'").fetchone()["status"] == "active"
        finally:
            conn.close()


# ------------------------------------------------------------------ 5. thu hồi phiên
def test_e2e_phien_bi_thu_hoi_tra_303_login(client, owner):
    # Tắt Brain để test không phụ thuộc dịch vụ ngoài (revoke sẽ bỏ qua bước gọi Brain).
    conn = db.connect()
    try:
        db.set_setting(conn, "brain.enabled", "0", "test-ag05")
        conn.commit()
    finally:
        conn.close()
    dang_nhap(client, "anh-thanh", "Owner!Passw0rd")
    tao_user("employee", "e2e-emp-02", dept="kinh-doanh")
    with _client() as emp:
        assert dang_nhap(emp, "e2e-emp-02", "User!Passw0rd").status_code == 303
        assert emp.get("/").status_code == 200
        token = csrf_cua(client)
        r = client.post("/tai-khoan/e2e-emp-02/thu-hoi-phien", data={"_csrf": token},
                        follow_redirects=False)
        assert r.status_code == 303

        home = emp.get("/", follow_redirects=False)
        assert home.status_code == 303
        assert "/dang-nhap" in home.headers["location"]
        assert emp.get("/api/me").status_code == 401
        conn = db.connect()
        try:
            rows = conn.execute("SELECT status FROM sessions WHERE user_id='e2e-emp-02'").fetchall()
            assert rows and all(r["status"] != "active" for r in rows)
        finally:
            conn.close()


# ------------------------------------------------------------------ 6. luồng B1–B5
def test_e2e_chu_so_huu_tao_quan_tri_roi_tao_nhan_vien(client, owner):
    dang_nhap(client, "anh-thanh", "Owner!Passw0rd")
    mat_khau_admin = "QaAdmin!Passw0rd"
    r = _tao_qua_http(client, {
        "id": "e2e-admin-01", "display_name": "E2E Quản trị", "role_code": "admin",
        "department_id": "ban-dieu-hanh", "scope_mode": "tenant",
        "password": mat_khau_admin, "must_change": "0",
    })
    assert r.status_code == 200 and "Đã tạo tài khoản" in r.text
    conn = db.connect()
    try:
        row = conn.execute("SELECT role_code, status, tenant_id FROM users "
                           "WHERE id='e2e-admin-01'").fetchone()
        assert row["role_code"] == "admin" and row["status"] == "active"
        assert conn.execute("SELECT department_id FROM admin_scopes WHERE user_id='e2e-admin-01'"
                            ).fetchone()["department_id"] is None
    finally:
        conn.close()

    with _client() as admin:
        assert dang_nhap(admin, "e2e-admin-01", mat_khau_admin).status_code == 303
        assert admin.get("/api/me").json()["data"]["vaiTro"] == "admin"
        r = _tao_qua_http(admin, {
            "id": "e2e-emp-03", "display_name": "E2E Nhân viên", "role_code": "employee",
            "department_id": "kinh-doanh", "password": "QaEmp!Passw0rd", "must_change": "0",
        })
        assert r.status_code == 200 and "Đã tạo tài khoản" in r.text
        conn = db.connect()
        try:
            row = conn.execute("SELECT role_code, department_id, created_by FROM users "
                               "WHERE id='e2e-emp-03'").fetchone()
            assert row["role_code"] == "employee"
            assert row["department_id"] == "kinh-doanh"
            assert row["created_by"] == "e2e-admin-01"
        finally:
            conn.close()

    with _client() as emp:
        assert dang_nhap(emp, "e2e-emp-03", "QaEmp!Passw0rd").status_code == 303
        me = emp.get("/api/me").json()["data"]
        assert me["modules"] == ["dashboard", "brain", "tasks", "knowledge", "usage"]
        hrefs = _sidebar_hrefs(emp.get("/").text)
        conn = db.connect()
        try:
            routes = {r["code"]: r["route"] for r in
                      conn.execute("SELECT code, route FROM modules WHERE status='active'")}
        finally:
            conn.close()
        assert hrefs == {routes[c] for c in me["modules"]}
        for route in ROUTES_QUAN_TRI:
            assert emp.get(route).status_code == 403


# ------------------------------------------------------------------ 7. Brain tắt
def test_e2e_brain_tat_khong_phat_ticket(client, owner):
    conn = db.connect()
    try:
        # Tắt module Brain ở tầng cài đặt (DB thắng env) để không gọi dịch vụ ngoài.
        db.set_setting(conn, "brain.enabled", "0", "test-ag05")
        conn.commit()
    finally:
        conn.close()
    tao_user("employee", "e2e-emp-04", dept="kinh-doanh")
    with _client() as emp:
        assert dang_nhap(emp, "e2e-emp-04", "User!Passw0rd").status_code == 303
        assert emp.get("/brain").status_code == 200
        token = csrf_cua(emp)
        r = emp.post("/brain/mo", data={"_csrf": token}, follow_redirects=False)
        assert r.status_code == 303
        location = r.headers.get("location", "")
        assert location.startswith("/brain"), "Brain tắt thì phải quay lại /brain"
        assert "ticket" not in location.lower(), "Không được phát ticket khi Brain tắt"
