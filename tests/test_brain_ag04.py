"""AG-04 — kiểm thử chính sách ánh xạ vai trò và shadow user của bridge COWORK.

Bridge là một tệp được COPY vào `app/api/` của Brain, nên nó dùng import tương đối
(`from .. import cau_hinh`, `from ..store import ...`). Để kiểm thử được logic thuần
mà không cần dựng cả Brain, tệp này nạp bridge dưới một gói `app.api` giả với các
module phụ thuộc tối thiểu. Không chạy mạng, không đọc DB thật.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "brain-bridge" / "cowork_bridge.py"


@pytest.fixture(scope="module")
def bridge():
    """Nạp brain-bridge/cowork_bridge.py với gói `app` giả; dọn sys.modules sau."""
    ten = ["app", "app.api", "app.cau_hinh", "app.store", "app.store.audit_repo",
           "app.store.db", "app.store.sessions_repo", "app.api.cowork_bridge"]
    da_co = {n: sys.modules[n] for n in ten if n in sys.modules}
    app = types.ModuleType("app")
    app.__path__ = []
    api = types.ModuleType("app.api")
    api.__path__ = []
    cau_hinh = types.ModuleType("app.cau_hinh")
    cau_hinh.gio_vn = lambda: "2026-10-19T17:00:00+07:00"
    cau_hinh.mfa_bat = lambda: False
    cau_hinh.mfa_user_id = lambda: ""
    store = types.ModuleType("app.store")
    store.__path__ = []
    audit_repo = types.ModuleType("app.store.audit_repo")
    db = types.ModuleType("app.store.db")
    db.ket_noi = lambda: None
    sessions_repo = types.ModuleType("app.store.sessions_repo")
    sessions_repo.HAN_GIO = 24
    sessions_repo.tao = lambda *a, **k: {}
    sys.modules.update({
        "app": app, "app.api": api, "app.cau_hinh": cau_hinh, "app.store": store,
        "app.store.audit_repo": audit_repo, "app.store.db": db,
        "app.store.sessions_repo": sessions_repo,
    })
    spec = importlib.util.spec_from_file_location("app.api.cowork_bridge", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["app.api.cowork_bridge"] = mod
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for n in ten:
            if n in da_co:
                sys.modules[n] = da_co[n]
            else:
                sys.modules.pop(n, None)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE tenants(id TEXT PRIMARY KEY, ten TEXT, taoLuc TEXT);
        CREATE TABLE users(
            id TEXT PRIMARY KEY, tenantId TEXT NOT NULL, ten TEXT, vaiTro TEXT, taoLuc TEXT,
            matKhauHash BLOB, salt BLOB, trangThai TEXT DEFAULT 'chua-kich-hoat');
        CREATE TABLE project_permissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, tenantId TEXT NOT NULL,
            userId TEXT NOT NULL, duAnId TEXT NOT NULL,
            quyen TEXT NOT NULL DEFAULT 'doc', UNIQUE(tenantId, userId, duAnId));
    """)
    c.execute("INSERT INTO tenants(id, ten) VALUES('vip-group', 'VIP Group')")
    c.commit()
    try:
        yield c
    finally:
        c.close()


@pytest.mark.parametrize(("user_id", "vai_tro", "mong"), [
    ("anh-thanh", "super_admin", "chu-so-huu"),
    ("super-02", "super_admin", "quan-tri"),
    ("quan-tri-01", "admin", "thanh-vien"),
    ("quan-tri-scope", "department_manager", "thanh-vien"),
    ("nhan-vien-01", "employee", "thanh-vien"),
    ("doi-tac-01", "partner", "thanh-vien"),
    ("vai-la", "", "thanh-vien"),
])
def test_anh_xa_vai_tro_fail_closed(bridge, user_id, vai_tro, mong):
    """Chỉ super_admin COWORK được lên quản trị Brain; mọi vai khác hạ xuống thành viên."""
    assert bridge._vai_tro_brain(user_id, vai_tro) == mong


def test_shadow_user_chi_duoc_quyen_doc_du_an_chung(bridge, conn):
    ok, _ = bridge._dam_bao_nguoi_dung(
        conn, {"id": "nhan-vien-01", "ten": "Nhân viên", "vaiTro": "employee"}, "vip-group")
    assert ok
    row = conn.execute("SELECT vaiTro, trangThai FROM users WHERE id='nhan-vien-01'").fetchone()
    assert (row["vaiTro"], row["trangThai"]) == ("thanh-vien", "hoat-dong")
    quyen = [tuple(r) for r in conn.execute(
        "SELECT duAnId, quyen FROM project_permissions WHERE userId='nhan-vien-01'")]
    assert quyen == [("tong-hop", "doc")]  # chỉ dự án chung, chỉ đọc


def test_shadow_user_goi_lai_khong_nhan_doi_quyen(bridge, conn):
    user = {"id": "nhan-vien-01", "vaiTro": "employee"}
    assert bridge._dam_bao_nguoi_dung(conn, user, "vip-group")[0]
    assert bridge._dam_bao_nguoi_dung(conn, user, "vip-group")[0]
    assert conn.execute("SELECT COUNT(*) FROM project_permissions").fetchone()[0] == 1


def test_admin_cowork_ha_xuong_thanh_vien_va_chi_doc_chung(bridge, conn):
    ok, _ = bridge._dam_bao_nguoi_dung(
        conn, {"id": "quan-tri-01", "vaiTro": "admin"}, "vip-group")
    assert ok
    assert conn.execute("SELECT vaiTro FROM users WHERE id='quan-tri-01'").fetchone()[0] == "thanh-vien"
    quyen = [tuple(r) for r in conn.execute(
        "SELECT duAnId, quyen FROM project_permissions WHERE userId='quan-tri-01'")]
    assert quyen == [("tong-hop", "doc")]


def test_tai_khoan_native_co_mat_khau_khong_bi_cap_them_quyen(bridge, conn):
    """Tài khoản native có mật khẩu không được tự động cấp dự án chung."""
    conn.execute("INSERT INTO users(id, tenantId, ten, vaiTro, trangThai, matKhauHash, salt) "
                 "VALUES('ke-toan-vien', 'vip-group', 'Kế toán', 'thanh-vien', 'hoat-dong', ?, ?)",
                 (b"hash", b"salt"))
    conn.commit()
    ok, _ = bridge._dam_bao_nguoi_dung(
        conn, {"id": "ke-toan-vien", "vaiTro": "employee"}, "vip-group")
    assert ok
    assert conn.execute("SELECT COUNT(*) FROM project_permissions").fetchone()[0] == 0


def test_shadow_cu_chua_co_quyen_duoc_backfill(bridge, conn):
    """Shadow cũ (không mật khẩu, chưa có quyền dự án) được backfill đúng một dòng đọc."""
    conn.execute("INSERT INTO users(id, tenantId, ten, vaiTro, trangThai) "
                 "VALUES('nhan-vien-cu', 'vip-group', 'Nhân viên cũ', 'thanh-vien', 'hoat-dong')")
    conn.commit()
    ok, _ = bridge._dam_bao_nguoi_dung(
        conn, {"id": "nhan-vien-cu", "vaiTro": "employee"}, "vip-group")
    assert ok
    quyen = [tuple(r) for r in conn.execute(
        "SELECT duAnId, quyen FROM project_permissions WHERE userId='nhan-vien-cu'")]
    assert quyen == [("tong-hop", "doc")]


def test_tai_khoan_da_co_quyen_du_an_khac_khong_bi_mo_them(bridge, conn):
    """Đã có quyền dự án (dù hẹp) thì không tự thêm dự án chung."""
    conn.execute("INSERT INTO users(id, tenantId, ten, vaiTro, trangThai) "
                 "VALUES('ke-toan-vien', 'vip-group', 'Kế toán', 'thanh-vien', 'hoat-dong')")
    conn.execute("INSERT INTO project_permissions(tenantId, userId, duAnId, quyen) "
                 "VALUES('vip-group', 'ke-toan-vien', 'ke-toan', 'ghi')")
    conn.commit()
    ok, _ = bridge._dam_bao_nguoi_dung(
        conn, {"id": "ke-toan-vien", "vaiTro": "employee"}, "vip-group")
    assert ok
    quyen = [tuple(r) for r in conn.execute(
        "SELECT duAnId, quyen FROM project_permissions WHERE userId='ke-toan-vien'")]
    assert quyen == [("ke-toan", "ghi")]


def test_sai_tenant_bi_tu_choi(bridge, conn):
    ok, ly_do = bridge._dam_bao_nguoi_dung(
        conn, {"id": "nhan-vien-01", "vaiTro": "employee"}, "tenant-khac")
    assert not ok and "Tenant" in ly_do
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
