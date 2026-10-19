"""Kiểm thử vận hành do controller bổ sung: IP sau proxy, logout thu hồi Brain."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import csrf_cua, dang_nhap, tao_user

from cowork import audit, auth, config, db, rbac, services, web
from cowork.errors import Forbidden


class ReqGia:
    def __init__(self, headers=None, host="127.0.0.1"):
        self.headers = headers or {}
        self.client = SimpleNamespace(host=host)


def test_ip_bo_qua_header_khi_khong_tin_proxy(monkeypatch):
    monkeypatch.setattr(config, "TIN_PROXY", False)
    req = ReqGia({"x-real-ip": "203.0.113.9", "x-forwarded-for": "198.51.100.7"})
    assert web.ip_cua(req) == "127.0.0.1"
    assert audit._ip(req) == "127.0.0.1"


def test_ip_tin_header_khi_bat_tin_proxy(monkeypatch):
    monkeypatch.setattr(config, "TIN_PROXY", True)
    req = ReqGia({"x-real-ip": "203.0.113.9", "x-forwarded-for": "198.51.100.7, 10.0.0.1"})
    assert web.ip_cua(req) == "203.0.113.9"
    assert audit._ip(req) == "203.0.113.9"


def test_ip_header_gia_khong_hop_le_bi_bo(monkeypatch):
    monkeypatch.setattr(config, "TIN_PROXY", True)
    req = ReqGia({"x-real-ip": "khong-phai-ip"})
    assert web.ip_cua(req) == "127.0.0.1"
    assert audit._ip(req) == "127.0.0.1"


def test_dang_xuat_thu_hoi_phien_brain(client, owner, monkeypatch):
    dang_nhap(client, "anh-thanh", "Owner!Passw0rd")
    csrf = csrf_cua(client)
    goi = {"dem": 0, "user": None}

    def fake(conn, user_id, ly_do="COWORK thu hồi quyền"):
        goi["dem"] += 1
        goi["user"] = user_id
        return {"ok": True, "http": 200}

    monkeypatch.setattr("cowork.brain.thu_hoi_phien", fake)
    r = client.post("/dang-xuat", data={"_csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/dang-nhap"
    assert goi["dem"] == 1
    assert goi["user"] == "anh-thanh"


def test_route_la_tra_trang_404_html_va_api_json(client):
    r = client.get("/khong-ton-tai-controller")
    assert r.status_code == 404
    assert "Không tìm thấy" in r.text
    api = client.get("/api/khong-ton-tai-controller")
    assert api.status_code == 404
    assert api.headers["content-type"].startswith("application/json")
    assert api.json()["ok"] is False


def test_tenant_b_khong_sua_cau_hinh_toan_cuc(client, owner):
    conn = db.connect()
    try:
        services.tao_super_admin(conn, "b-cfg", "Bcfg!Passw0rd", "b-cfg", tenant_id="tenant-b")
        actor = auth.nguoi_dung_day_du(conn, "b-cfg")
        perms = rbac.quyen_hieu_luc(conn, actor)
        with pytest.raises(Forbidden):
            services.cap_nhat_cai_dat(conn, actor, perms, {"tenant.display_name": "HACK"})
        with pytest.raises(Forbidden):
            services.cap_nhat_module(conn, actor, perms,
                                     rbac.module_theo_code(conn, "tasks"), {"status": "disabled"})
        with pytest.raises(Forbidden):
            services.cap_nhat_quyen_vai_tro(conn, actor, perms, "admin", ["dashboard.view"])
    finally:
        conn.close()


def test_thong_ke_nhan_vien_khong_lo_so_ban_toan_tenant(client, owner):
    tao_user("employee", "emp-tk", dept="kinh-doanh")
    conn = db.connect()
    try:
        user = auth.nguoi_dung_day_du(conn, "emp-tk")
        perms = rbac.quyen_hieu_luc(conn, user)
        tk = services.thong_ke(conn, user, perms)
        assert tk["tongNguoiDung"] == 1
        assert tk["soBan"] == 1  # chỉ ban của mình, không phải tổng số ban tenant
    finally:
        conn.close()


def test_luu_tru_admin_don_admin_scopes(client, owner):
    tao_user("admin", "arch-admin", dept="ban-dieu-hanh", scope_mode="tenant")
    conn = db.connect()
    try:
        actor = auth.nguoi_dung_day_du(conn, "anh-thanh")
        perms = rbac.quyen_hieu_luc(conn, actor)
        target = auth.nguoi_dung_day_du(conn, "arch-admin")
        assert conn.execute("SELECT COUNT(*) FROM admin_scopes WHERE user_id='arch-admin'"
                            ).fetchone()[0] == 1
        services.luu_tru_nguoi_dung(conn, actor, perms, target)
        assert conn.execute("SELECT COUNT(*) FROM admin_scopes WHERE user_id='arch-admin'"
                            ).fetchone()[0] == 0
    finally:
        conn.close()


def test_module_khong_co_quyen_use_bi_khoa_trong_ui(client, owner):
    tao_user("employee", "emp-ui-use", dept="kinh-doanh")
    conn = db.connect()
    try:
        target = auth.nguoi_dung_day_du(conn, "emp-ui-use")
        states = {m["code"]: m for m in services.trang_thai_quyen_module(conn, target)}
        assert states["dashboard"]["has_use"] is False
        assert states["brain"]["has_use"] is True
    finally:
        conn.close()
    dang_nhap(client, "anh-thanh", "Owner!Passw0rd")
    html = client.get("/tai-khoan/emp-ui-use/phan-quyen").text
    assert "Module không có mức sử dụng" in html


def test_head_root_tra_200(client):
    assert client.head("/").status_code == 200


def test_dashboard_co_nut_mo_brain_truc_tiep(client, owner):
    dang_nhap(client, "anh-thanh", "Owner!Passw0rd")
    html = client.get("/").text
    assert 'action="/brain/mo"' in html
    assert "Mở VIP AI Brain" in html


def test_csp_cho_phep_form_redirect_sang_brain(client):
    from urllib.parse import urlsplit
    from cowork import config
    r = client.get("/dang-nhap")
    csp = r.headers.get("content-security-policy", "")
    parts = urlsplit(config.BRAIN_PUBLIC_URL)
    origin = f"{parts.scheme}://{parts.netloc}"
    assert "form-action 'self' " + origin in csp
