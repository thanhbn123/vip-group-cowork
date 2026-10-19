"""Kiểm thử bảo mật & nghiệp vụ COWORK."""
from __future__ import annotations

import json
import sqlite3

import pytest
from conftest import csrf_cua, csrf_tu, dang_nhap, tao_user

from cowork import auth, brain, db, rbac, security, services
from cowork.errors import Forbidden


def test_dang_nhap_thanh_cong_va_cookie_an(client, owner):
    r = dang_nhap(client, "anh-thanh", "Owner!Passw0rd")
    assert r.status_code == 303
    cookie = r.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    home = client.get("/")
    assert home.status_code == 200
    assert "Bảng điều khiển" in home.text


def test_dang_nhap_sai_va_khoa_tam(client, owner):
    for _ in range(5):
        r = dang_nhap(client, "anh-thanh", "SaiMatKhau!", follow=True)
        assert r.status_code == 200
    r = dang_nhap(client, "anh-thanh", "Owner!Passw0rd", follow=True)
    assert "tạm khoá" in r.text.lower()
    conn = db.connect()
    try:
        so = conn.execute("SELECT COUNT(*) FROM login_attempts WHERE success=0").fetchone()[0]
        assert so >= 5
    finally:
        conn.close()


def test_nhan_vien_chi_thay_module_duoc_cap(client, owner):
    tao_user("employee", "emp-01", dept="kinh-doanh")
    dang_nhap(client, "emp-01", "User!Passw0rd")
    me = client.get("/api/me").json()["data"]
    assert me["modules"] == ["dashboard", "brain", "tasks", "knowledge", "usage"]
    assert client.get("/tai-khoan").status_code == 403
    assert client.get("/ban").status_code == 403
    assert client.get("/cai-dat").status_code == 403
    assert client.get("/nhat-ky").status_code == 403


def test_quan_tri_khong_tao_duoc_super_admin(client, owner):
    tao_user("admin", "admin-01", dept="ban-dieu-hanh")
    dang_nhap(client, "admin-01", "User!Passw0rd")
    page = client.get("/tai-khoan/tao-moi")
    csrf = csrf_tu(page.text)
    r = client.post("/tai-khoan/tao-moi", data={
        "_csrf": csrf, "id": "super-gia", "display_name": "Super Giả",
        "role_code": "super_admin", "password": "SuperGia!123",
    })
    assert r.status_code == 400
    assert "Super Admin" in r.text
    conn = db.connect()
    try:
        assert conn.execute("SELECT 1 FROM users WHERE id='super-gia'").fetchone() is None
    finally:
        conn.close()


def test_quan_tri_khong_sua_duoc_super_admin(client, owner):
    tao_user("admin", "admin-02", dept="ban-dieu-hanh")
    dang_nhap(client, "admin-02", "User!Passw0rd")
    csrf = csrf_cua(client)
    r = client.post("/tai-khoan/anh-thanh", data={
        "_csrf": csrf, "display_name": "HACKED", "role_code": "admin",
    }, follow_redirects=False)
    assert r.status_code == 303
    conn = db.connect()
    try:
        row = conn.execute("SELECT display_name, role_code FROM users WHERE id='anh-thanh'").fetchone()
        assert row["display_name"] == "anh-thanh"
        assert row["role_code"] == "super_admin"
    finally:
        conn.close()


def test_quan_tri_theo_ban_khong_thao_tac_ngoai_pham_vi(client, owner):
    tao_user("admin", "scope-01", dept="kinh-doanh", scope_mode="departments",
             scope_departments=["kinh-doanh"])
    dang_nhap(client, "scope-01", "User!Passw0rd")
    danh_sach = client.get("/tai-khoan").text
    assert "anh-thanh" not in danh_sach
    assert "emp-01" not in danh_sach
    csrf = csrf_tu(client.get("/tai-khoan/tao-moi").text)
    r = client.post("/tai-khoan/tao-moi", data={
        "_csrf": csrf, "id": "nv-ky-thuat", "display_name": "Kỹ thuật",
        "role_code": "employee", "department_id": "ky-thuat", "password": "Kt01!Passw0rd",
    })
    assert r.status_code == 400
    assert "phạm vi" in r.text


def test_cach_ly_tenant(client, owner):
    conn = db.connect()
    try:
        services.tao_super_admin(conn, "b-admin", "Badmin!Passw0rd", "b-admin", tenant_id="tenant-b")
    finally:
        conn.close()
    # Tạo user tenant B bằng actor tenant B
    conn = db.connect()
    try:
        actor = auth.nguoi_dung_day_du(conn, "b-admin")
        perms = rbac.quyen_hieu_luc(conn, actor)
        services.tao_nguoi_dung(conn, actor, perms, {
            "id": "b-user", "display_name": "B User", "role_code": "admin",
            "password": "Buser!Passw0rd", "must_change": "0", "scope_mode": "tenant",
        })
    finally:
        conn.close()
    dang_nhap(client, "b-admin", "Badmin!Passw0rd")
    assert client.get("/api/me").json()["data"]["tenantId"] == "tenant-b"
    assert client.get("/tai-khoan/anh-thanh").status_code == 404
    assert "anh-thanh" not in client.get("/tai-khoan").text
    csrf = csrf_cua(client)
    assert client.post("/tai-khoan/anh-thanh/khoa", data={"_csrf": csrf}).status_code == 404


def test_thu_hoi_quyen_module_co_hieu_luc_ngay(client, owner):
    tao_user("employee", "emp-02", dept="kinh-doanh")
    dang_nhap(client, "emp-02", "User!Passw0rd")
    assert "brain" in client.get("/api/me").json()["data"]["modules"]
    conn = db.connect()
    try:
        actor = auth.nguoi_dung_day_du(conn, "anh-thanh")
        perms = rbac.quyen_hieu_luc(conn, actor)
        target = auth.nguoi_dung_day_du(conn, "emp-02")
        services.dat_quyen_module(conn, actor, perms, target, {"brain": "block"})
    finally:
        conn.close()
    assert "brain" not in client.get("/api/me").json()["data"]["modules"]
    assert client.get("/brain").status_code == 403


def test_thu_hoi_phien_chan_ngay(client, owner):
    tao_user("employee", "emp-03", dept="kinh-doanh")
    dang_nhap(client, "emp-03", "User!Passw0rd")
    assert client.get("/").status_code == 200
    conn = db.connect()
    try:
        auth.thu_hoi_cua_user(conn, "emp-03", "anh-thanh", "test")
    finally:
        conn.close()
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert "/dang-nhap" in r.headers["location"]


def test_thieu_csrf_bi_chan(client, owner):
    dang_nhap(client, "anh-thanh", "Owner!Passw0rd")
    r = client.post("/tai-khoan/tao-moi", data={
        "id": "no-csrf", "display_name": "No CSRF", "role_code": "employee",
        "department_id": "kinh-doanh", "password": "NoCsrf!12345",
    })
    assert r.status_code == 403
    conn = db.connect()
    try:
        assert conn.execute("SELECT 1 FROM users WHERE id='no-csrf'").fetchone() is None
    finally:
        conn.close()


def test_audit_append_only(client, owner):
    conn = db.connect()
    try:
        before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        assert before >= 1
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE audit_log SET action='x' WHERE id=1")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_log WHERE id=1")
    finally:
        conn.close()


def test_brain_ticket_dung_mot_lan_va_hmac(client, owner):
    tao_user("employee", "emp-04", dept="kinh-doanh")
    conn = db.connect()
    try:
        user = auth.nguoi_dung_day_du(conn, "emp-04")
        ticket = brain.tao_ticket(conn, user, None, "127.0.0.1")
        kq = brain.tieu_ticket(conn, ticket)
        assert kq and kq["user"]["id"] == "emp-04"
        assert brain.tieu_ticket(conn, ticket) is None  # one-time
        ticket2 = brain.tao_ticket(conn, user, None, "127.0.0.1")
    finally:
        conn.close()
    body = json.dumps({"ticket": ticket2}).encode()
    bad = client.post("/api/internal/brain/consume", content=body,
                      headers={"X-Cowork-Ts": "1", "X-Cowork-Sig": "sai",
                               "Content-Type": "application/json"})
    assert bad.status_code == 401
    headers = {"Content-Type": "application/json",
               **security.ky_hmac("brain->cowork", body)}
    ok = client.post("/api/internal/brain/consume", content=body, headers=headers)
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["user"]["id"] == "emp-04" and "brain.use" in data["quyen"]
    again = client.post("/api/internal/brain/consume", content=body, headers=headers)
    assert again.status_code == 401


def test_quan_tri_khong_cap_duoc_quyen(client, owner):
    tao_user("admin", "admin-03", dept="ban-dieu-hanh")
    tao_user("employee", "emp-05", dept="kinh-doanh")
    conn = db.connect()
    try:
        actor = auth.nguoi_dung_day_du(conn, "admin-03")
        perms = rbac.quyen_hieu_luc(conn, actor)
        target = auth.nguoi_dung_day_du(conn, "emp-05")
        with pytest.raises(Forbidden):
            services.dat_quyen_module(conn, actor, perms, target, {"brain": "block"})
        assert conn.execute(
            "SELECT COUNT(*) FROM user_permissions WHERE user_id='emp-05'").fetchone()[0] == 0
    finally:
        conn.close()


def test_mat_khau_chi_luu_dang_bam(client, owner):
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT password_hash, password_salt FROM users WHERE id='anh-thanh'").fetchone()
        assert row["password_hash"] and row["password_hash"] != "Owner!Passw0rd"
        assert row["password_salt"]
        assert not security.kiem_mat_khau("SaiMatKhau!", row["password_hash"], row["password_salt"])
        assert security.kiem_mat_khau("Owner!Passw0rd", row["password_hash"], row["password_salt"])
    finally:
        conn.close()
