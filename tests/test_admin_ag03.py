"""AG-03 — kiểm thử đối kháng Admin & RBAC.

Mục tiêu: chứng minh Super Admin bất khả xâm phạm, quản trị được uỷ quyền không
leo thang/không vượt phạm vi, tenant tách biệt, audit đúng actor/target và không
lộ mật khẩu. Các test chạy trên HTTP thật + service thật; không mock PASS.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from conftest import csrf_cua, dang_nhap, tao_user
from fastapi.testclient import TestClient

from cowork import auth, db, rbac, services
from cowork.errors import Conflict, Forbidden
from cowork.main import app

MK = "User!Passw0rd"
SUPER_MK = "Owner!Passw0rd"


# ------------------------------------------------------------------ tiện ích
@contextmanager
def _db():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _login(user_id: str, mat_khau: str = MK):
    with TestClient(app) as c:
        r = dang_nhap(c, user_id, mat_khau)
        assert r.status_code == 303, f"đăng nhập {user_id} thất bại ({r.status_code})"
        yield c


def _post(c: TestClient, url: str, data: dict | None = None):
    payload = {"_csrf": csrf_cua(c)}
    payload.update(data or {})
    return c.post(url, data=payload, follow_redirects=False)


def _actor(user_id: str):
    with _db() as conn:
        user = auth.nguoi_dung_day_du(conn, user_id)
        return user, rbac.quyen_hieu_luc(conn, user)


def _user(user_id: str):
    with _db() as conn:
        return auth.nguoi_dung_day_du(conn, user_id)


def _sid(user_id: str) -> str:
    with _db() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE user_id=? AND status='active' "
            "ORDER BY created_at DESC", (user_id,)).fetchone()
        assert row, f"{user_id} không có phiên hoạt động"
        return row["id"]


def _session_status(session_id: str) -> str:
    with _db() as conn:
        row = conn.execute("SELECT status FROM sessions WHERE id=?", (session_id,)).fetchone()
        assert row, f"không thấy phiên {session_id}"
        return row["status"]


def _cap_quyen_bo_sung(user_id: str, *codes: str, effect: str = "allow") -> None:
    """Tạo uỷ quyền riêng trực tiếp — mô phỏng dữ liệu uỷ quyền đã tồn tại."""
    with _db() as conn:
        target = auth.nguoi_dung_day_du(conn, user_id)
        for code in codes:
            conn.execute(
                "INSERT OR REPLACE INTO user_permissions(tenant_id, user_id, permission_code, "
                "effect, granted_by, granted_at) VALUES(?,?,?,?,?,?)",
                (target["tenant_id"], user_id, code, effect, "ag03-setup", db.now_iso()))
        conn.commit()


def _du_lieu_cap_nhat(user: dict, **ghi_de) -> dict:
    data = {
        "display_name": user["display_name"],
        "email": user.get("email") or "",
        "phone": user.get("phone") or "",
        "role_code": user["role_code"],
        "department_id": user.get("department_id") or "",
        "partner_org": user.get("partner_org") or "",
    }
    data.update(ghi_de)
    return data


def _tao_tenant_b() -> None:
    with _db() as conn:
        services.tao_super_admin(conn, "b-admin", "Badmin!Passw0rd", "b-admin",
                                 tenant_id="tenant-b")


def _tao_ban_b() -> None:
    with _db() as conn:
        actor = auth.nguoi_dung_day_du(conn, "b-admin")
        perms = rbac.quyen_hieu_luc(conn, actor)
        services.tao_ban(conn, actor, perms, {"name": "Ban B", "code": "ban-b"})


# ------------------------------------------------------------------ 1. Super Admin
def test_super_admin_khong_bi_thay_doi_boi_admin(owner):
    tao_user("admin", "admin-01", dept="ban-dieu-hanh")
    with _db() as conn:
        truoc = dict(conn.execute("SELECT * FROM users WHERE id='anh-thanh'").fetchone())

    with _login("anh-thanh", SUPER_MK) as sup:
        sup_sid = _sid("anh-thanh")
        with _login("admin-01") as admin:
            r = _post(admin, "/tai-khoan/anh-thanh", _du_lieu_cap_nhat(
                _user("anh-thanh"), display_name="HACKED", role_code="admin",
                department_id="ban-dieu-hanh"))
            assert r.status_code == 303
            assert _post(admin, "/tai-khoan/anh-thanh/khoa").status_code == 303
            assert _post(admin, "/tai-khoan/anh-thanh/mo-khoa").status_code == 303
            assert _post(admin, "/tai-khoan/anh-thanh/luu-tru").status_code == 303
            assert _post(admin, "/tai-khoan/anh-thanh/dat-lai-mat-khau").status_code == 303
            assert _post(admin, "/tai-khoan/anh-thanh/phan-quyen",
                         {"quyen_brain": "block"}).status_code == 303
            assert _post(admin, "/tai-khoan/anh-thanh/thu-hoi-phien").status_code == 403
            assert _post(admin, f"/tai-khoan/anh-thanh/phien/{sup_sid}/thu-hoi").status_code == 403
            assert _post(admin, "/tai-khoan/anh-thanh/pham-vi",
                         {"scope_mode": "departments"}).status_code == 403
        assert sup.get("/api/me").status_code == 200

    with _db() as conn:
        sau = dict(conn.execute("SELECT * FROM users WHERE id='anh-thanh'").fetchone())
        assert sau["display_name"] == truoc["display_name"]
        assert sau["role_code"] == rbac.SUPER
        assert sau["status"] == "active"
        assert sau["password_hash"] == truoc["password_hash"]
        assert sau["department_id"] is None
        assert conn.execute("SELECT COUNT(*) FROM user_permissions WHERE user_id='anh-thanh'"
                            ).fetchone()[0] == 0
        assert conn.execute("SELECT status FROM sessions WHERE id=?", (sup_sid,)
                            ).fetchone()["status"] == "active"
        assert rbac.dem_super_admin(conn, "vip-group") == 1

        admin = auth.nguoi_dung_day_du(conn, "admin-01")
        perms = rbac.quyen_hieu_luc(conn, admin)
        target = auth.nguoi_dung_day_du(conn, "anh-thanh")
        for thao_tac in (
            lambda: services.cap_nhat_nguoi_dung(
                conn, admin, perms, target, _du_lieu_cap_nhat(target, role_code="admin")),
            lambda: services.doi_trang_thai(conn, admin, perms, target, "suspended"),
            lambda: services.luu_tru_nguoi_dung(conn, admin, perms, target),
            lambda: services.dat_lai_mat_khau(conn, admin, perms, target),
            lambda: services.dat_quyen_module(conn, admin, perms, target, {"brain": "block"}),
        ):
            with pytest.raises(Forbidden):
                thao_tac()
        assert rbac.dem_super_admin(conn, "vip-group") == 1


def test_khong_tao_duoc_super_admin_thu_hai(owner):
    with _login("anh-thanh", SUPER_MK) as c:
        page = c.get("/tai-khoan/tao-moi")
        assert page.status_code == 200
        assert 'value="super_admin"' not in page.text
        r = _post(c, "/tai-khoan/tao-moi", {
            "id": "super-gia", "display_name": "Super Giả", "role_code": "super_admin",
            "password": "SuperGia!Pass123", "must_change": "0",
        })
        assert r.status_code == 400
        assert "Super Admin" in r.text
    with _db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE role_code='super_admin'"
                            ).fetchone()[0] == 1
        assert conn.execute("SELECT 1 FROM users WHERE id='super-gia'").fetchone() is None
        actor = auth.nguoi_dung_day_du(conn, "anh-thanh")
        perms = rbac.quyen_hieu_luc(conn, actor)
        with pytest.raises(Forbidden):
            services.tao_nguoi_dung(conn, actor, perms, {
                "id": "super-gia-2", "display_name": "Super Giả 2",
                "role_code": "super_admin", "password": "SuperGia!Pass456",
                "must_change": "0",
            })

    tao_user("admin", "admin-01", dept="ban-dieu-hanh")
    with _login("admin-01") as c:
        r = _post(c, "/tai-khoan/tao-moi", {
            "id": "super-gia-3", "display_name": "Super Giả 3", "role_code": "super_admin",
            "password": "SuperGia!Pass789", "must_change": "0",
        })
        assert r.status_code == 400
    with _db() as conn:
        assert conn.execute("SELECT 1 FROM users WHERE id='super-gia-3'").fetchone() is None
        assert rbac.dem_super_admin(conn, "vip-group") == 1


def test_admin_khong_tu_nang_quyen(owner):
    tao_user("admin", "admin-self", dept="ban-dieu-hanh")
    with _db() as conn:
        hash_truoc = conn.execute("SELECT password_hash FROM users WHERE id='admin-self'"
                                  ).fetchone()[0]
    with _login("admin-self") as c:
        assert _post(c, "/tai-khoan/admin-self", _du_lieu_cap_nhat(
            _user("admin-self"), display_name="HACKED SELF", role_code="employee",
            department_id="kinh-doanh")).status_code == 303
        assert _post(c, "/tai-khoan/admin-self/khoa").status_code == 303
        assert _post(c, "/tai-khoan/admin-self/luu-tru").status_code == 303
        assert _post(c, "/tai-khoan/admin-self/dat-lai-mat-khau").status_code == 303
        assert _post(c, "/tai-khoan/admin-self/phan-quyen",
                     {"quyen_brain": "block"}).status_code == 303
        assert _post(c, "/tai-khoan/admin-self/pham-vi",
                     {"scope_mode": "departments", "scope_departments": []}).status_code == 403
        assert c.get("/api/me").status_code == 200

    with _db() as conn:
        row = dict(conn.execute("SELECT * FROM users WHERE id='admin-self'").fetchone())
        assert row["display_name"] == "admin-self"
        assert row["role_code"] == rbac.ADMIN
        assert row["status"] == "active"
        assert row["password_hash"] == hash_truoc
        assert conn.execute("SELECT COUNT(*) FROM user_permissions WHERE user_id='admin-self'"
                            ).fetchone()[0] == 0
        scope = conn.execute("SELECT department_id FROM admin_scopes WHERE user_id='admin-self'"
                             ).fetchall()
        assert len(scope) == 1 and scope[0]["department_id"] is None

        target = auth.nguoi_dung_day_du(conn, "admin-self")
        perms = rbac.quyen_hieu_luc(conn, target)
        for thao_tac in (
            lambda: services.cap_nhat_nguoi_dung(
                conn, target, perms, target, _du_lieu_cap_nhat(target, role_code="employee")),
            lambda: services.doi_trang_thai(conn, target, perms, target, "suspended"),
            lambda: services.luu_tru_nguoi_dung(conn, target, perms, target),
            lambda: services.dat_lai_mat_khau(conn, target, perms, target),
            lambda: services.dat_quyen_module(conn, target, perms, target, {"brain": "block"}),
        ):
            with pytest.raises(Forbidden):
                thao_tac()


# ------------------------------------------------------------------ 2. uỷ quyền
def test_admin_scope_chi_trong_ban(owner):
    tao_user("admin", "scope-admin", dept="kinh-doanh", scope_mode="departments",
             scope_departments=["kinh-doanh"])
    tao_user("employee", "emp-trong", dept="kinh-doanh")
    tao_user("employee", "emp-ngoai", dept="ky-thuat")
    with _db() as conn:
        hash_ngoai = conn.execute("SELECT password_hash FROM users WHERE id='emp-ngoai'"
                                  ).fetchone()[0]

    with _login("scope-admin") as c:
        ds = c.get("/tai-khoan")
        assert "emp-trong" in ds.text
        assert "emp-ngoai" not in ds.text
        assert "anh-thanh" not in ds.text
        assert c.get("/tai-khoan/emp-ngoai").status_code == 403
        assert c.get("/tai-khoan/emp-trong").status_code == 200

        assert _post(c, "/tai-khoan/emp-ngoai", _du_lieu_cap_nhat(
            _user("emp-ngoai"), display_name="HACK NGOAI")).status_code == 303
        assert _post(c, "/tai-khoan/emp-ngoai/khoa").status_code == 303
        assert _post(c, "/tai-khoan/emp-ngoai/luu-tru").status_code == 303
        assert _post(c, "/tai-khoan/emp-ngoai/dat-lai-mat-khau").status_code == 303
        assert _post(c, "/tai-khoan/emp-ngoai/phan-quyen",
                     {"quyen_brain": "block"}).status_code == 303
        assert _post(c, "/tai-khoan/emp-ngoai/thu-hoi-phien").status_code == 403
        assert c.get("/tai-khoan/emp-ngoai/phan-quyen").status_code == 403
        assert _post(c, "/tai-khoan/emp-trong", _du_lieu_cap_nhat(
            _user("emp-trong"), display_name="Trong Ban Đã Sửa")).status_code == 303

        ban = c.get("/ban")
        assert "Ban Kinh doanh" in ban.text
        assert "Ban Kỹ thuật" not in ban.text
        assert c.get("/ban/ky-thuat").status_code == 403
        assert _post(c, "/ban/ky-thuat", {"name": "HACK BAN", "description": ""}).status_code == 303

        # Không tạo được ngang cấp/cao hơn; tạo được vai trò thấp hơn trong ban.
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "admin-moi", "display_name": "Admin Mới", "role_code": "admin",
            "department_id": "kinh-doanh", "password": "AdminMoi!Pass123",
            "must_change": "0", "scope_mode": "tenant",
        }).status_code == 400
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "mgr-moi", "display_name": "Trưởng Ban Mới",
            "role_code": "department_manager", "department_id": "kinh-doanh",
            "password": "MgrMoi!Pass123", "must_change": "0",
        }).status_code == 200
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "mgr-ngoai", "display_name": "Trưởng Ban Ngoài",
            "role_code": "department_manager", "department_id": "ky-thuat",
            "password": "MgrNgoai!Pass123", "must_change": "0",
        }).status_code == 400

    with _db() as conn:
        ngoai = dict(conn.execute("SELECT * FROM users WHERE id='emp-ngoai'").fetchone())
        assert ngoai["display_name"] == "emp-ngoai"
        assert ngoai["status"] == "active"
        assert ngoai["password_hash"] == hash_ngoai
        assert conn.execute("SELECT COUNT(*) FROM user_permissions WHERE user_id='emp-ngoai'"
                            ).fetchone()[0] == 0
        assert conn.execute("SELECT display_name FROM users WHERE id='emp-trong'"
                            ).fetchone()[0] == "Trong Ban Đã Sửa"
        assert conn.execute("SELECT name FROM departments WHERE id='ky-thuat'"
                            ).fetchone()[0] == "Ban Kỹ thuật"
        assert conn.execute("SELECT 1 FROM users WHERE id='admin-moi'").fetchone() is None
        assert conn.execute("SELECT 1 FROM users WHERE id='mgr-ngoai'").fetchone() is None
        assert conn.execute("SELECT role_code FROM users WHERE id='mgr-moi'"
                            ).fetchone()[0] == rbac.MANAGER

        actor = auth.nguoi_dung_day_du(conn, "scope-admin")
        perms = rbac.quyen_hieu_luc(conn, actor)
        target = auth.nguoi_dung_day_du(conn, "emp-ngoai")
        for thao_tac in (
            lambda: services.cap_nhat_nguoi_dung(
                conn, actor, perms, target, _du_lieu_cap_nhat(target, display_name="HACK")),
            lambda: services.doi_trang_thai(conn, actor, perms, target, "suspended"),
            lambda: services.luu_tru_nguoi_dung(conn, actor, perms, target),
            lambda: services.dat_lai_mat_khau(conn, actor, perms, target),
            lambda: services.dat_quyen_module(conn, actor, perms, target, {"brain": "block"}),
            lambda: rbac.kiem_tra_quan_ly(conn, actor, perms, target,
                                          "accounts.revoke_sessions"),
            lambda: services.tao_nguoi_dung(conn, actor, perms, {
                "id": "emp-lac", "display_name": "Ngoài Ban", "role_code": "employee",
                "department_id": "ky-thuat", "password": "EmpLac!Pass123",
                "must_change": "0",
            }),
        ):
            with pytest.raises(Forbidden):
                thao_tac()


def test_admin_scope_null_va_khong_dat_pham_vi_cho_nguoi_khac(owner):
    tao_user("admin", "admin-full", dept=None, scope_mode="tenant")
    tao_user("admin", "admin-scoped", dept="kinh-doanh", scope_mode="departments",
             scope_departments=["kinh-doanh"])
    tao_user("admin", "admin-noscope", dept="kinh-doanh", scope_mode="departments",
             scope_departments=[])
    tao_user("employee", "emp-kinh", dept="kinh-doanh")
    tao_user("employee", "emp-ky", dept="ky-thuat")

    with _db() as conn:
        full = auth.nguoi_dung_day_du(conn, "admin-full")
        scoped = auth.nguoi_dung_day_du(conn, "admin-scoped")
        noscope = auth.nguoi_dung_day_du(conn, "admin-noscope")
        assert rbac.pham_vi_ban(conn, full) is None
        assert rbac.pham_vi_ban(conn, scoped) == {"kinh-doanh"}
        assert rbac.pham_vi_ban(conn, noscope) == {"kinh-doanh"}
        assert conn.execute("SELECT COUNT(*) FROM admin_scopes WHERE user_id='admin-noscope'"
                            ).fetchone()[0] == 0

    with _login("admin-full") as c:
        ds = c.get("/tai-khoan")
        assert "emp-kinh" in ds.text and "emp-ky" in ds.text
    with _login("admin-scoped") as c:
        ds = c.get("/tai-khoan")
        assert "emp-kinh" in ds.text and "emp-ky" not in ds.text
        assert _post(c, "/tai-khoan/admin-full/pham-vi", {
            "scope_mode": "departments", "scope_departments": [],
        }).status_code == 403
    with _login("admin-noscope") as c:
        ds = c.get("/tai-khoan")
        assert "emp-kinh" in ds.text and "emp-ky" not in ds.text

    with _db() as conn:
        # Phạm vi toàn tenant của admin-full vẫn là NULL duy nhất, không bị đổi.
        rows = conn.execute("SELECT department_id FROM admin_scopes WHERE user_id='admin-full'"
                            ).fetchall()
        assert len(rows) == 1 and rows[0]["department_id"] is None
        actor = auth.nguoi_dung_day_du(conn, "admin-scoped")
        perms = rbac.quyen_hieu_luc(conn, actor)
        with pytest.raises(Forbidden):
            services._luu_scope_admin(conn, actor, "emp-kinh", {"scope_mode": "tenant"})
        assert conn.execute("SELECT COUNT(*) FROM admin_scopes WHERE user_id='emp-kinh'"
                            ).fetchone()[0] == 0


def test_roles_manage_bi_uy_quyen_khong_sua_vai_tro_ngang_cap(owner):
    tao_user("admin", "role-editor", dept="ban-dieu-hanh")
    _cap_quyen_bo_sung("role-editor", "roles.manage", "permissions.grant")
    with _db() as conn:
        actor = auth.nguoi_dung_day_du(conn, "role-editor")
        perms = rbac.quyen_hieu_luc(conn, actor)
        cu = {r["permission_code"] for r in conn.execute(
            "SELECT permission_code FROM role_permissions WHERE role_code='admin'").fetchall()}
        with pytest.raises(Forbidden):
            services.cap_nhat_quyen_vai_tro(conn, actor, perms, "admin", sorted(cu))
        moi = {r["permission_code"] for r in conn.execute(
            "SELECT permission_code FROM role_permissions WHERE role_code='admin'").fetchall()}
        assert moi == cu, "vai trò ngang cấp đã bị sửa"

        # Không được gán quyền chỉ Super Admin hoặc quyền mình không có cho vai trò thấp hơn.
        truoc = {r["permission_code"] for r in conn.execute(
            "SELECT permission_code FROM role_permissions WHERE role_code='department_manager'"
        ).fetchall()}
        with pytest.raises(Forbidden):
            services.cap_nhat_quyen_vai_tro(conn, actor, perms, "department_manager",
                                            sorted(truoc | {"settings.manage"}))
        with pytest.raises(Forbidden):
            services.cap_nhat_quyen_vai_tro(conn, actor, perms, "department_manager",
                                            sorted(truoc | {"accounts.archive"}))
        sau = {r["permission_code"] for r in conn.execute(
            "SELECT permission_code FROM role_permissions WHERE role_code='department_manager'"
        ).fetchall()}
        assert sau == truoc

        # Trong giới hạn: vai trò thấp hơn + subset quyền mình có thì được phép.
        ket_qua = services.cap_nhat_quyen_vai_tro(
            conn, actor, perms, "department_manager", ["dashboard.view", "brain.view"])
        assert ket_qua["them"] == []
        assert set(r["permission_code"] for r in conn.execute(
            "SELECT permission_code FROM role_permissions WHERE role_code='department_manager'"
        ).fetchall()) == {"dashboard.view", "brain.view"}

        with pytest.raises(Forbidden):
            services.cap_nhat_quyen_vai_tro(conn, actor, perms, "super_admin", ["dashboard.view"])


def test_super_khong_gan_duoc_quyen_chi_super_cho_vai_tro_khac(owner):
    with _db() as conn:
        actor = auth.nguoi_dung_day_du(conn, "anh-thanh")
        perms = rbac.quyen_hieu_luc(conn, actor)
        cu = {r["permission_code"] for r in conn.execute(
            "SELECT permission_code FROM role_permissions WHERE role_code='admin'").fetchall()}
        for quyen in ("roles.manage", "modules.manage", "settings.manage", "settings.view"):
            with pytest.raises(Forbidden):
                services.cap_nhat_quyen_vai_tro(conn, actor, perms, "admin",
                                                sorted(cu | {quyen}))
        moi = {r["permission_code"] for r in conn.execute(
            "SELECT permission_code FROM role_permissions WHERE role_code='admin'").fetchall()}
        assert moi == cu


def test_permissions_grant_subset_scope_va_nguyen_tu(owner):
    tao_user("admin", "grant-admin", dept="kinh-doanh", scope_mode="departments",
             scope_departments=["kinh-doanh"])
    tao_user("admin", "admin-peer", dept="kinh-doanh")
    tao_user("employee", "emp-grant", dept="kinh-doanh")
    tao_user("employee", "emp-out", dept="ky-thuat")
    _cap_quyen_bo_sung("grant-admin", "permissions.grant")
    # Quyền riêng có sẵn của emp-grant: chặn Brain.
    _cap_quyen_bo_sung("emp-grant", "brain.view", "brain.use", effect="deny")

    with _db() as conn:
        actor = auth.nguoi_dung_day_du(conn, "grant-admin")
        perms = rbac.quyen_hieu_luc(conn, actor)
        target = auth.nguoi_dung_day_du(conn, "emp-grant")
        assert services.trang_thai_quyen_module(conn, target)[1]["mode"] in ("block", "default")

        truoc_brain = {r["permission_code"]: r["effect"] for r in conn.execute(
            "SELECT permission_code, effect FROM user_permissions WHERE user_id='emp-grant'"
        ).fetchall()}
        so_audit = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='permissions.update'"
                                ).fetchone()[0]
        # Lựa chọn thứ hai bị từ chối ⇒ KHÔNG được thu hồi dở dang lựa chọn đầu.
        with pytest.raises(Forbidden):
            services.dat_quyen_module(conn, actor, perms, target,
                                      {"brain": "default", "settings": "use"})
        sau_brain = {r["permission_code"]: r["effect"] for r in conn.execute(
            "SELECT permission_code, effect FROM user_permissions WHERE user_id='emp-grant'"
        ).fetchall()}
        assert sau_brain == truoc_brain, "đã thu hồi dở dang trước khi bị từ chối"
        assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='permissions.update'"
                            ).fetchone()[0] == so_audit

        # Subset hợp lệ: cấp brain.use cho nhân viên trong phạm vi.
        thay_doi = services.dat_quyen_module(conn, actor, perms, target, {"brain": "use"})
        assert "brain" in thay_doi
        row = conn.execute("SELECT effect FROM user_permissions WHERE user_id='emp-grant' "
                           "AND permission_code='brain.use'").fetchone()
        assert row["effect"] == "allow"
        audit_row = conn.execute("SELECT actor_id, target_id FROM audit_log "
                                 "WHERE action='permissions.update' ORDER BY id DESC LIMIT 1"
                                 ).fetchone()
        assert audit_row["actor_id"] == "grant-admin" and audit_row["target_id"] == "emp-grant"

        # Quyền chỉ Super Admin: từ chối kể cả khi actor có quyền đó do dữ liệu cũ.
        _cap_quyen_bo_sung("grant-admin", "settings.view")
        actor = auth.nguoi_dung_day_du(conn, "grant-admin")
        perms = rbac.quyen_hieu_luc(conn, actor)
        with pytest.raises(Forbidden):
            services.dat_quyen_module(conn, actor, perms, target, {"settings": "view"})
        assert conn.execute("SELECT COUNT(*) FROM user_permissions WHERE user_id='emp-grant' "
                            "AND permission_code LIKE 'settings.%'").fetchone()[0] == 0

        # Sai phạm vi / khác cấp / Super Admin / tự mình: từ chối.
        for khoa in ("emp-out", "admin-peer", "anh-thanh", "grant-admin"):
            with pytest.raises(Forbidden):
                services.dat_quyen_module(conn, actor, perms,
                                          auth.nguoi_dung_day_du(conn, khoa),
                                          {"dashboard": "block"})


def test_module_va_cai_dat_chi_super(owner):
    tao_user("admin", "drift-admin", dept="ban-dieu-hanh")
    _cap_quyen_bo_sung("drift-admin", "modules.manage", "settings.manage")
    with _db() as conn:
        actor = auth.nguoi_dung_day_du(conn, "drift-admin")
        perms = rbac.quyen_hieu_luc(conn, actor)
        module = rbac.module_theo_code(conn, "tasks")
        with pytest.raises(Forbidden):
            services.cap_nhat_module(conn, actor, perms, module, {"status": "disabled"})
        assert rbac.module_theo_code(conn, "tasks")["status"] == "active"
        with pytest.raises(Forbidden):
            services.cap_nhat_cai_dat(conn, actor, perms, {"tenant.display_name": "HACK"})
        assert db.get_setting(conn, "tenant.display_name", "") == "VIP GROUP"

        # Super Admin vẫn dùng được (không chặn nhầm).
        sup = auth.nguoi_dung_day_du(conn, "anh-thanh")
        sup_perms = rbac.quyen_hieu_luc(conn, sup)
        services.cap_nhat_module(conn, sup, sup_perms, module, {"status": "disabled"})
        assert rbac.module_theo_code(conn, "tasks")["status"] == "disabled"


# ------------------------------------------------------------------ 3. Trưởng ban
def test_truong_ban_chi_thay_va_sua_trong_ban(owner):
    tao_user("department_manager", "mgr-kinh", dept="kinh-doanh")
    tao_user("employee", "emp-kinh", dept="kinh-doanh")
    tao_user("employee", "emp-ky", dept="ky-thuat")
    tao_user("department_manager", "mgr-ky", dept="ky-thuat")

    with _login("mgr-kinh") as c:
        ds = c.get("/tai-khoan")
        assert "emp-kinh" in ds.text
        assert "emp-ky" not in ds.text
        assert "mgr-ky" not in ds.text
        assert "anh-thanh" not in ds.text
        assert c.get("/tai-khoan/emp-ky").status_code == 403
        assert c.get("/tai-khoan/emp-kinh").status_code == 200
        assert c.get("/tai-khoan/emp-ky/phan-quyen").status_code == 403
        assert c.get("/tai-khoan/emp-kinh/phan-quyen").status_code == 200
        assert c.get("/ban").text.count("Ban Kinh doanh") >= 1
        assert "Ban Kỹ thuật" not in c.get("/ban").text
        assert c.get("/ban/ky-thuat").status_code == 403

        # Không tạo admin/manager ngang cấp, không tạo partner ngoài ban.
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "mgr-gia", "display_name": "Mgr Giả", "role_code": "department_manager",
            "department_id": "kinh-doanh", "password": "MgrGia!Pass123", "must_change": "0",
        }).status_code == 400
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "admin-gia", "display_name": "Admin Giả", "role_code": "admin",
            "department_id": "kinh-doanh", "password": "AdminGia!Pass123", "must_change": "0",
        }).status_code == 400
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "dt-ngoai", "display_name": "Đối Tác Ngoài", "role_code": "partner",
            "department_id": "ky-thuat", "partner_org": "HĐ ngoài",
            "password": "DoiTac!Pass123", "must_change": "0",
        }).status_code == 400
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "nv-ngoai", "display_name": "Nhân Viên Ngoài", "role_code": "employee",
            "department_id": "ky-thuat", "password": "NvNgoai!Pass123", "must_change": "0",
        }).status_code == 400
        # Trong ban được tạo nhân viên và đối tác.
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "nv-trong", "display_name": "Nhân Viên Trong", "role_code": "employee",
            "department_id": "kinh-doanh", "password": "NvTrong!Pass123", "must_change": "0",
        }).status_code == 200
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "dt-trong", "display_name": "Đối Tác Trong", "role_code": "partner",
            "department_id": "kinh-doanh", "partner_org": "HĐ trong",
            "password": "DoiTacTrong!Pass123", "must_change": "0",
        }).status_code == 200

        # Manager không có accounts.update: sửa bị chặn.
        assert _post(c, "/tai-khoan/emp-kinh", _du_lieu_cap_nhat(
            _user("emp-kinh"), display_name="Manager Sửa")).status_code == 303
        assert _user("emp-kinh")["display_name"] == "emp-kinh"

        # Manager không thể thao tác Super Admin.
        assert _post(c, "/tai-khoan/anh-thanh", _du_lieu_cap_nhat(
            _user("anh-thanh"), display_name="HACK SUPER")).status_code == 303
        assert _post(c, "/tai-khoan/anh-thanh/thu-hoi-phien").status_code == 403

    # Uỷ quyền thêm accounts.update: vẫn chỉ sửa trong ban, không tự nâng mình.
    _cap_quyen_bo_sung("mgr-kinh", "accounts.update")
    with _login("mgr-kinh") as c:
        assert _post(c, "/tai-khoan/emp-kinh", _du_lieu_cap_nhat(
            _user("emp-kinh"), display_name="Manager Sửa Trong Ban")).status_code == 303
        assert _post(c, "/tai-khoan/emp-ky", _du_lieu_cap_nhat(
            _user("emp-ky"), display_name="HACK NGOAI BAN")).status_code == 303
        assert _post(c, "/tai-khoan/mgr-kinh", _du_lieu_cap_nhat(
            _user("mgr-kinh"), display_name="HACK SELF", role_code="admin",
            department_id="kinh-doanh")).status_code == 303

    with _db() as conn:
        assert conn.execute("SELECT display_name FROM users WHERE id='emp-kinh'"
                            ).fetchone()[0] == "Manager Sửa Trong Ban"
        assert conn.execute("SELECT display_name FROM users WHERE id='emp-ky'"
                            ).fetchone()[0] == "emp-ky"
        assert conn.execute("SELECT display_name, role_code FROM users WHERE id='mgr-kinh'"
                            ).fetchone()["role_code"] == rbac.MANAGER
        assert conn.execute("SELECT display_name FROM users WHERE id='anh-thanh'"
                            ).fetchone()[0] == "anh-thanh"
        assert conn.execute("SELECT 1 FROM users WHERE id IN ('mgr-gia','admin-gia','dt-ngoai','nv-ngoai')"
                            ).fetchone() is None
        assert conn.execute("SELECT role_code FROM users WHERE id='nv-trong'"
                            ).fetchone()[0] == rbac.EMPLOYEE
        assert conn.execute("SELECT role_code FROM users WHERE id='dt-trong'"
                            ).fetchone()[0] == rbac.PARTNER

        actor = auth.nguoi_dung_day_du(conn, "mgr-kinh")
        perms = rbac.quyen_hieu_luc(conn, actor)
        target = auth.nguoi_dung_day_du(conn, "emp-ky")
        for hanh_dong in ("accounts.update", "accounts.reset_password", "accounts.suspend",
                          "accounts.archive", "accounts.revoke_sessions", "permissions.grant"):
            with pytest.raises(Forbidden):
                rbac.kiem_tra_quan_ly(conn, actor, perms, target, hanh_dong)


# ------------------------------------------------------------------ 4. tenant
def test_cach_ly_tenant_nguoi_dung_ban_audit(owner):
    tao_user("employee", "a-emp", dept="kinh-doanh")
    _tao_tenant_b()
    _tao_ban_b()
    tao_user("admin", "b-quan-tri", actor_id="b-admin")
    tao_user("employee", "b-emp", dept="ban-b", actor_id="b-admin")

    with _login("b-quan-tri") as c:
        ds = c.get("/tai-khoan")
        assert "b-emp" in ds.text
        assert "a-emp" not in ds.text and "anh-thanh" not in ds.text
        assert c.get("/tai-khoan/a-emp").status_code == 404
        assert _post(c, "/tai-khoan/a-emp", {"display_name": "HACK A"}).status_code == 404
        assert c.get("/ban/kinh-doanh").status_code == 404
        assert _post(c, "/ban/kinh-doanh", {"name": "HACK A BAN"}).status_code == 404
        nhat_ky = c.get("/nhat-ky")
        assert nhat_ky.status_code == 200
        assert "a-emp" not in nhat_ky.text

    with _login("b-admin", "Badmin!Passw0rd") as c:
        assert _post(c, "/tai-khoan/a-emp/khoa").status_code == 404
        # Không đặt được phạm vi bằng ban của tenant khác.
        assert _post(c, "/tai-khoan/b-quan-tri/pham-vi", {
            "scope_mode": "departments", "scope_departments": ["kinh-doanh"],
        }).status_code == 303

    with _db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM admin_scopes WHERE user_id='b-quan-tri' "
            "AND department_id='kinh-doanh'").fetchone()[0] == 0

        # Audit tách tenant tuyệt đối.
        from cowork import audit as audit_mod
        b_rows = audit_mod.liet_ke(conn, "tenant-b", page_size=200)["rows"]
        assert b_rows
        assert all(r["tenant_id"] == "tenant-b" for r in b_rows)
        assert all(r["target_id"] != "a-emp" for r in b_rows)
        a_rows = audit_mod.liet_ke(conn, "vip-group", page_size=200)["rows"]
        assert any(r["target_id"] == "a-emp" for r in a_rows)

        # Dòng admin_scopes giả mạo trỏ sang ban của tenant khác phải bị bỏ qua.
        tao_user("admin", "a-admin-noscope", dept="kinh-doanh", scope_mode="departments",
                 scope_departments=[])
        conn.execute(
            "INSERT INTO admin_scopes(tenant_id, user_id, department_id, created_at, created_by) "
            "VALUES(?,?,?,?,?)",
            ("vip-group", "a-admin-noscope", "ban-b", db.now_iso(), "ag03-setup"))
        conn.commit()
        a_admin = auth.nguoi_dung_day_du(conn, "a-admin-noscope")
        assert rbac.pham_vi_ban(conn, a_admin) == {"kinh-doanh"}


# ------------------------------------------------------------------ 5. phiên
def test_thu_hoi_phien_phai_dung_chu_so_huu(owner):
    tao_user("admin", "scope-admin", dept="kinh-doanh", scope_mode="departments",
             scope_departments=["kinh-doanh"])
    tao_user("employee", "emp-trong", dept="kinh-doanh")
    tao_user("employee", "emp-ngoai", dept="ky-thuat")

    # 1) Admin trong phạm vi emp-trong không được thu hồi phiên của emp-ngoai.
    with _login("emp-ngoai") as victim:
        victim_sid = _sid("emp-ngoai")
        with _login("scope-admin") as attacker:
            r = _post(attacker, f"/tai-khoan/emp-trong/phien/{victim_sid}/thu-hoi")
            assert r.status_code == 303
        assert _session_status(victim_sid) == "active"
        assert victim.get("/api/me").status_code == 200
    with _db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE actor_id='scope-admin' "
                            "AND target_id=?", (victim_sid,)).fetchone()[0] == 0

    # 2) Không thu hồi được phiên Super Admin qua URL.
    with _login("anh-thanh", SUPER_MK) as sup:
        sup_sid = _sid("anh-thanh")
        with _login("scope-admin") as attacker:
            assert _post(attacker,
                         f"/tai-khoan/anh-thanh/phien/{sup_sid}/thu-hoi").status_code == 403
        assert _session_status(sup_sid) == "active"
        assert sup.get("/api/me").status_code == 200

    # 3) Tenant B không thu hồi được phiên của tenant A.
    _tao_tenant_b()
    _tao_ban_b()
    tao_user("admin", "b-quan-tri", actor_id="b-admin")
    tao_user("employee", "b-emp", dept="ban-b", actor_id="b-admin")
    with _login("anh-thanh", SUPER_MK) as sup:
        sup_sid = _sid("anh-thanh")
        with _login("b-quan-tri") as attacker:
            r = _post(attacker, f"/tai-khoan/b-emp/phien/{sup_sid}/thu-hoi")
            assert r.status_code == 303
        assert _session_status(sup_sid) == "active"
    with _db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE actor_id='b-quan-tri' "
                            "AND target_id=?", (sup_sid,)).fetchone()[0] == 0

    # 4) Thu hồi đúng phiên của đúng người vẫn hoạt động.
    with _login("emp-trong") as victim:
        victim_sid = _sid("emp-trong")
        with _login("scope-admin") as attacker:
            assert _post(attacker,
                         f"/tai-khoan/emp-trong/phien/{victim_sid}/thu-hoi").status_code == 303
        assert _session_status(victim_sid) == "revoked"
        assert victim.get("/", follow_redirects=False).status_code == 303


# ------------------------------------------------------------------ 6. audit
def test_audit_dung_actor_target_va_khong_lo_mat_khau(owner):
    mat_khau_tao = "Audit!Pass123"
    mat_khau_sai = "KhongBaoGioDung!456"
    with _login("anh-thanh", SUPER_MK) as c:
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "audit-user", "display_name": "Audit User", "email": "audit@test.local",
            "role_code": "employee", "department_id": "kinh-doanh",
            "password": mat_khau_tao, "must_change": "0",
        }).status_code == 200
        assert _post(c, "/tai-khoan/audit-user", _du_lieu_cap_nhat(
            _user("audit-user"), display_name="Audit User Đã Sửa")).status_code == 303

    with _db() as conn:
        sup = auth.nguoi_dung_day_du(conn, "anh-thanh")
        sup_perms = rbac.quyen_hieu_luc(conn, sup)
        target = auth.nguoi_dung_day_du(conn, "audit-user")
        services.dat_quyen_module(conn, sup, sup_perms, target, {"brain": "block"})
        temp = services.dat_lai_mat_khau(conn, sup, sup_perms, target)

    with _login("anh-thanh", SUPER_MK) as c:
        assert _post(c, "/tai-khoan/audit-user/khoa").status_code == 303

    with _db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM audit_log WHERE target_id='audit-user' ORDER BY id").fetchall()]
        actions = {r["action"] for r in rows}
        assert {"account.create", "account.update", "account.reset_password",
                "account.suspend", "permissions.update"} <= actions
        for r in rows:
            if r["action"] == "auth.login":
                continue
            assert r["actor_id"] == "anh-thanh", r["action"]
            assert r["actor_role"] == "super_admin", r["action"]
            assert r["target_id"] == "audit-user", r["action"]

        tat_ca = [dict(r) for r in conn.execute("SELECT detail FROM audit_log").fetchall()]
        for secret in (mat_khau_tao, mat_khau_sai, temp, SUPER_MK):
            assert all(secret not in (r["detail"] or "") for r in tat_ca), \
                "audit làm lộ mật khẩu"

        status = conn.execute("SELECT status FROM users WHERE id='audit-user'").fetchone()[0]
        assert status == "suspended"


# ------------------------------------------------------------------ 7. archived
def test_tai_khoan_luu_tru_khong_bi_khoi_phuc_boi_admin(owner):
    # Role admin mặc định KHÔNG có accounts.archive (chỉ Super Admin); test này
    # chủ động cấp accounts.archive để kiểm luồng archive + bất biến sau archive.
    tao_user("admin", "admin-arch", dept="ban-dieu-hanh")
    _cap_quyen_bo_sung("admin-arch", "accounts.archive")
    tao_user("employee", "emp-arch", dept="kinh-doanh", mat_khau="EmpArch!Pass123")
    with _db() as conn:
        hash_truoc = conn.execute("SELECT password_hash FROM users WHERE id='emp-arch'"
                                  ).fetchone()[0]
    with _login("emp-arch", "EmpArch!Pass123"):
        emp_sid = _sid("emp-arch")

    with _login("admin-arch") as c:
        assert _post(c, "/tai-khoan/emp-arch/luu-tru").status_code == 303
        assert _session_status(emp_sid) == "revoked"
        assert _post(c, "/tai-khoan/emp-arch/mo-khoa").status_code == 303
        assert _post(c, "/tai-khoan/emp-arch", _du_lieu_cap_nhat(
            _user("emp-arch"), display_name="HỒI SINH")).status_code == 303
        assert _post(c, "/tai-khoan/emp-arch/dat-lai-mat-khau").status_code == 303
        assert _post(c, "/tai-khoan/emp-arch/phan-quyen",
                     {"quyen_brain": "default"}).status_code == 303
        assert _post(c, "/tai-khoan/emp-arch/thu-hoi-phien").status_code == 403
        assert _post(c, "/tai-khoan/emp-arch/luu-tru").status_code == 303

    with _db() as conn:
        row = dict(conn.execute("SELECT * FROM users WHERE id='emp-arch'").fetchone())
        assert row["status"] == "archived"
        assert row["display_name"] == "emp-arch"
        assert row["password_hash"] == hash_truoc
        assert conn.execute("SELECT COUNT(*) FROM user_permissions WHERE user_id='emp-arch'"
                            ).fetchone()[0] == 0
        actor = auth.nguoi_dung_day_du(conn, "admin-arch")
        perms = rbac.quyen_hieu_luc(conn, actor)
        target = auth.nguoi_dung_day_du(conn, "emp-arch")
        for thao_tac in (
            lambda: services.doi_trang_thai(conn, actor, perms, target, "active"),
            lambda: services.cap_nhat_nguoi_dung(
                conn, actor, perms, target, _du_lieu_cap_nhat(target, display_name="HACK")),
            lambda: services.dat_lai_mat_khau(conn, actor, perms, target),
            lambda: services.dat_quyen_module(conn, actor, perms, target, {"brain": "use"}),
            lambda: services.luu_tru_nguoi_dung(conn, actor, perms, target),
        ):
            with pytest.raises(Forbidden):
                thao_tac()

    # Tài khoản đã lưu trữ không đăng nhập được.
    with TestClient(app) as c:
        assert dang_nhap(c, "emp-arch", "EmpArch!Pass123").status_code == 303
        assert c.get("/api/me").status_code == 401

    # Super Admin vẫn khôi phục được.
    with _db() as conn:
        sup = auth.nguoi_dung_day_du(conn, "anh-thanh")
        sup_perms = rbac.quyen_hieu_luc(conn, sup)
        target = auth.nguoi_dung_day_du(conn, "emp-arch")
        services.doi_trang_thai(conn, sup, sup_perms, target, "active")
        assert conn.execute("SELECT status FROM users WHERE id='emp-arch'"
                            ).fetchone()[0] == "active"


# ------------------------------------------------------------------ 8. gán trưởng ban
def test_cap_nhat_ban_khong_di_chuyen_super_hoac_nguoi_ngoai_pham_vi(owner):
    tao_user("admin", "dept-admin", dept="kinh-doanh", scope_mode="departments",
             scope_departments=["kinh-doanh"])
    tao_user("admin", "admin-ky", dept="ky-thuat")
    tao_user("department_manager", "mgr-kinh", dept="kinh-doanh")
    tao_user("department_manager", "mgr-ky", dept="ky-thuat")

    with _login("dept-admin") as c:
        du_lieu = {"name": "Ban Kinh doanh", "description": "Mô tả",
                   "manager_user_id": "anh-thanh"}
        assert _post(c, "/ban/kinh-doanh", du_lieu).status_code == 303
        du_lieu["manager_user_id"] = "admin-ky"
        assert _post(c, "/ban/kinh-doanh", du_lieu).status_code == 303
        du_lieu["manager_user_id"] = "mgr-ky"
        assert _post(c, "/ban/kinh-doanh", du_lieu).status_code == 303

        page = c.get("/ban/kinh-doanh")
        assert page.status_code == 200
        assert "anh-thanh" not in page.text
        assert "admin-ky" not in page.text
        assert "mgr-ky" not in page.text
        assert "mgr-kinh" in page.text

        du_lieu["manager_user_id"] = "mgr-kinh"
        assert _post(c, "/ban/kinh-doanh", du_lieu).status_code == 303

    with _db() as conn:
        assert conn.execute("SELECT department_id FROM users WHERE id='anh-thanh'"
                            ).fetchone()[0] is None
        assert conn.execute("SELECT department_id FROM users WHERE id='admin-ky'"
                            ).fetchone()[0] == "ky-thuat"
        assert conn.execute("SELECT department_id FROM users WHERE id='mgr-ky'"
                            ).fetchone()[0] == "ky-thuat"
        assert conn.execute("SELECT manager_user_id FROM departments WHERE id='kinh-doanh'"
                            ).fetchone()[0] == "mgr-kinh"

        actor = auth.nguoi_dung_day_du(conn, "dept-admin")
        perms = rbac.quyen_hieu_luc(conn, actor)
        dept = dict(conn.execute("SELECT * FROM departments WHERE id='kinh-doanh'").fetchone())
        with pytest.raises(Forbidden):
            services.cap_nhat_ban(conn, actor, perms, dept,
                                  {"name": "HACK", "manager_user_id": "anh-thanh"})
        assert conn.execute("SELECT department_id FROM users WHERE id='anh-thanh'"
                            ).fetchone()[0] is None


# ------------------------------------------------------------------ 9. uỷ quyền tầng sâu
def test_employee_duoc_cap_quyen_khong_thao_tac_ngoai_ban(owner):
    tao_user("employee", "emp-delegate", dept="kinh-doanh")
    tao_user("partner", "doi-tac-ky", dept="ky-thuat")
    _cap_quyen_bo_sung("emp-delegate", "accounts.update", "accounts.suspend",
                       "accounts.create")
    with _db() as conn:
        actor = auth.nguoi_dung_day_du(conn, "emp-delegate")
        perms = rbac.quyen_hieu_luc(conn, actor)
        target = auth.nguoi_dung_day_du(conn, "doi-tac-ky")
        assert rbac.pham_vi_ban(conn, actor) == set()
        for thao_tac in (
            lambda: services.cap_nhat_nguoi_dung(
                conn, actor, perms, target, _du_lieu_cap_nhat(target, display_name="HACK")),
            lambda: services.doi_trang_thai(conn, actor, perms, target, "suspended"),
            lambda: services.tao_nguoi_dung(conn, actor, perms, {
                "id": "dt-moi", "display_name": "Đối Tác Mới", "role_code": "partner",
                "department_id": "ky-thuat", "partner_org": "HĐ mới",
                "password": "DoiTacMoi!Pass123", "must_change": "0",
            }),
        ):
            with pytest.raises(Forbidden):
                thao_tac()

    with _login("emp-delegate") as c:
        assert _post(c, "/tai-khoan/doi-tac-ky", _du_lieu_cap_nhat(
            _user("doi-tac-ky"), display_name="HACK WEB")).status_code == 303
        assert _post(c, "/tai-khoan/doi-tac-ky/khoa").status_code == 303
        assert _post(c, "/tai-khoan/tao-moi", {
            "id": "dt-web", "display_name": "Đối Tác Web", "role_code": "partner",
            "department_id": "ky-thuat", "partner_org": "HĐ web",
            "password": "DoiTacWeb!Pass123", "must_change": "0",
        }).status_code == 400

    with _db() as conn:
        assert conn.execute("SELECT display_name, status FROM users WHERE id='doi-tac-ky'"
                            ).fetchone()["status"] == "active"
        assert conn.execute("SELECT display_name FROM users WHERE id='doi-tac-ky'"
                            ).fetchone()[0] == "doi-tac-ky"
        assert conn.execute("SELECT 1 FROM users WHERE id IN ('dt-moi','dt-web')"
                            ).fetchone() is None


# ------------------------------------------------------------------ 10. ban & tenant
def test_tao_ban_trung_ma_tenant_khac_khong_500(owner):
    _tao_tenant_b()
    with _login("b-admin", "Badmin!Passw0rd") as c:
        r = _post(c, "/ban/tao-moi", {
            "name": "Ban Trùng Mã", "code": "kinh-doanh", "description": "",
        })
        assert r.status_code == 400, "mã ban trùng tenant khác phải trả lỗi nghiệp vụ, không 500"
        assert _post(c, "/ban/tao-moi", {
            "name": "Ban B", "code": "ban-b", "description": "",
        }).status_code == 303
    with _db() as conn:
        assert conn.execute("SELECT tenant_id FROM departments WHERE id='kinh-doanh'"
                            ).fetchone()[0] == "vip-group"
        assert conn.execute("SELECT tenant_id FROM departments WHERE id='ban-b'"
                            ).fetchone()[0] == "tenant-b"
        actor = auth.nguoi_dung_day_du(conn, "b-admin")
        perms = rbac.quyen_hieu_luc(conn, actor)
        with pytest.raises(Conflict):
            services.tao_ban(conn, actor, perms, {"name": "Trùng", "code": "kinh-doanh"})
        assert conn.execute("SELECT COUNT(*) FROM departments WHERE id='kinh-doanh'"
                            ).fetchone()[0] == 1


# ------------------------------------------------------------------ 11. mở khoá & rate limit
def test_mo_khoa_xoa_bo_dem_dang_nhap_sai_cua_target(owner):
    """5 lần sai → khoá → mở khoá phải đăng nhập đúng được ngay.

    Chỉ xoá bộ đếm của target, không xoá của người khác.
    """
    tao_user("employee", "emp-lock", dept="kinh-doanh", mat_khau="EmpLock!Pass123")
    tao_user("employee", "emp-khac", dept="kinh-doanh", mat_khau="EmpKhac!Pass123")
    tao_user("admin", "admin-lock", dept="ban-dieu-hanh")

    with TestClient(app) as c:
        for _ in range(5):
            assert dang_nhap(c, "emp-lock", "SaiMatKhau!999").status_code == 303
        for _ in range(3):
            assert dang_nhap(c, "emp-khac", "SaiMatKhau!999").status_code == 303

    # Đang bị rate-limit: mật khẩu đúng vẫn bị trả về trang đăng nhập.
    with TestClient(app) as c:
        r = dang_nhap(c, "emp-lock", "EmpLock!Pass123")
        assert r.status_code == 303
        assert "/dang-nhap" in r.headers["location"]
        assert c.get("/api/me").status_code == 401

    with _login("admin-lock") as c:
        assert _post(c, "/tai-khoan/emp-lock/khoa").status_code == 303
        assert _user("emp-lock")["status"] == "suspended"
        assert _post(c, "/tai-khoan/emp-lock/mo-khoa").status_code == 303
        assert _user("emp-lock")["status"] == "active"

    with _db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM login_attempts "
                            "WHERE user_id='emp-lock' AND success=0").fetchone()[0] == 0
        # Không xoá oan bộ đếm của tài khoản khác.
        assert conn.execute("SELECT COUNT(*) FROM login_attempts "
                            "WHERE user_id='emp-khac' AND success=0").fetchone()[0] == 3

    with TestClient(app) as c:
        r = dang_nhap(c, "emp-lock", "EmpLock!Pass123")
        assert r.status_code == 303
        assert "/dang-nhap" not in r.headers["location"]
        assert c.get("/api/me").status_code == 200
        assert c.get("/api/me").json()["data"]["id"] == "emp-lock"


# ------------------------------------------------------------------ 12. module không có quyền use
def test_bon_muc_quyen_khong_lam_500_module_khong_co_use(owner):
    """accounts/departments… chỉ có view+action, không có `<module>.use`.

    Trước đây chọn 'block'/'view'/'use' cho các module này ghi mã `use` không
    tồn tại ⇒ FOREIGN KEY constraint failed (500). Bốn mức phải chạy an toàn.
    """
    tao_user("employee", "emp-mode", dept="kinh-doanh")
    with _login("anh-thanh", SUPER_MK) as c:
        assert _post(c, "/tai-khoan/emp-mode/phan-quyen", {
            "quyen_accounts": "block",
        }).status_code == 303

    with _db() as conn:
        sup = auth.nguoi_dung_day_du(conn, "anh-thanh")
        sup_perms = rbac.quyen_hieu_luc(conn, sup)
        target = auth.nguoi_dung_day_du(conn, "emp-mode")
        states = {r["code"]: r for r in services.trang_thai_quyen_module(conn, target)}
        assert states["accounts"]["mode"] == "block"
        assert states["accounts"]["effective"] == "block"
        assert conn.execute("SELECT 1 FROM user_permissions WHERE user_id='emp-mode' "
                            "AND permission_code='accounts.use'").fetchone() is None

        # view + use cho module không có `use` không được tạo mã ma.
        services.dat_quyen_module(conn, sup, sup_perms, target, {"departments": "view"})
        services.dat_quyen_module(conn, sup, sup_perms, target, {"dashboard": "block"})
        states = {r["code"]: r for r in services.trang_thai_quyen_module(conn, target)}
        assert states["dashboard"]["effective"] == "block"
        services.dat_quyen_module(conn, sup, sup_perms, target, {"dashboard": "use"})
        assert conn.execute("SELECT 1 FROM user_permissions WHERE user_id='emp-mode' "
                            "AND permission_code LIKE '%.use' "
                            "AND permission_code IN ('dashboard.use','departments.use')"
                            ).fetchone() is None
        states = {r["code"]: r for r in services.trang_thai_quyen_module(conn, target)}
        assert states["departments"]["effective"] == "view"
        assert states["dashboard"]["effective"] == "view"


# ------------------------------------------------------------------ 13. thống kê audit
def test_thong_ke_audit_khong_ro_ri_tenant_cho_nhan_vien(owner):
    tao_user("employee", "emp-stat", dept="kinh-doanh")
    tao_user("employee", "emp-stat-2", dept="kinh-doanh")
    with _db() as conn:
        emp = auth.nguoi_dung_day_du(conn, "emp-stat")
        perms = rbac.quyen_hieu_luc(conn, emp)
        tong = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE tenant_id='vip-group' AND created_at>=?",
            (db.today_iso(),)).fetchone()[0]
        rieng = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE tenant_id='vip-group' AND actor_id='emp-stat' "
            "AND created_at>=?", (db.today_iso(),)).fetchone()[0]
        tk = services.thong_ke(conn, emp, perms)
        assert tk["auditHomNay"] == rieng
        assert tk["auditHomNay"] < tong, "nhân viên không được thấy số audit toàn tenant"

    # Đăng nhập tạo thêm audit của chính emp-stat; số hiển thị vẫn chỉ của họ.
    with _login("emp-stat"):
        pass
    with _db() as conn:
        emp = auth.nguoi_dung_day_du(conn, "emp-stat")
        perms = rbac.quyen_hieu_luc(conn, emp)
        rieng = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE tenant_id='vip-group' AND actor_id='emp-stat' "
            "AND created_at>=?", (db.today_iso(),)).fetchone()[0]
        assert services.thong_ke(conn, emp, perms)["auditHomNay"] == rieng
