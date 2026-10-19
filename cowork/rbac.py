"""RBAC: quyền hiệu lực, module hiển thị, phạm vi quản trị, chống leo thang."""
from __future__ import annotations

import sqlite3

from .errors import Forbidden
from . import security

SUPER = "super_admin"
ADMIN = "admin"
MANAGER = "department_manager"
EMPLOYEE = "employee"
PARTNER = "partner"

#: Quyền miễn nhiễm: chỉ Super Admin mới có, không thể uỷ quyền qua user_permissions.
QUYEN_CHI_SUPER = {
    "roles.manage", "modules.manage", "settings.manage", "settings.view",
}


def lay_nguoi_dung(conn: sqlite3.Connection, user_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def lay_vai_tro(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute("SELECT * FROM roles WHERE code=?", (code,)).fetchone()
    return dict(row) if row else None


def cap_vai_tro(conn: sqlite3.Connection, code: str) -> int:
    row = conn.execute("SELECT level FROM roles WHERE code=?", (code,)).fetchone()
    return int(row["level"]) if row else 0


def la_super(user: dict | None) -> bool:
    return bool(user) and user.get("role_code") == SUPER


def quyen_hieu_luc(conn: sqlite3.Connection, user: dict) -> set[str]:
    """Quyền của vai trò + allow riêng − deny riêng. Super Admin luôn đủ quyền."""
    if la_super(user):
        return {r["code"] for r in conn.execute("SELECT code FROM permissions").fetchall()}
    perms = {r["permission_code"] for r in conn.execute(
        "SELECT permission_code FROM role_permissions WHERE role_code=?",
        (user["role_code"],)).fetchall()}
    for r in conn.execute(
            "SELECT permission_code, effect FROM user_permissions WHERE user_id=?",
            (user["id"],)).fetchall():
        if r["effect"] == "allow":
            perms.add(r["permission_code"])
        else:
            perms.discard(r["permission_code"])
    return perms


def co_quyen(user: dict, perms: set[str], quyen: str) -> bool:
    if la_super(user):
        return True
    return quyen in perms


def doi_quyen(user: dict, perms: set[str], quyen: str, thong_bao: str = "") -> None:
    if not co_quyen(user, perms, quyen):
        raise Forbidden(thong_bao or f"Bạn không có quyền '{quyen}'.")


def module_hien_thi(conn: sqlite3.Connection, user: dict, perms: set[str]) -> list[dict]:
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM modules WHERE status='active' ORDER BY group_code DESC, sort_order, code"
    ).fetchall()]
    # group_code: 'workspace' trước 'admin' — sắp theo bảng chữ cái giảm dần cho ổn định,
    # nên sắp lại tường minh.
    rows.sort(key=lambda m: (0 if m["group_code"] == "workspace" else 1,
                             m["sort_order"], m["code"]))
    if la_super(user):
        return rows
    ra = []
    for m in rows:
        if f"{m['code']}.view" in perms:
            m = dict(m)
            m["co_use"] = f"{m['code']}.use" in perms
            ra.append(m)
    return ra


def module_theo_code(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute("SELECT * FROM modules WHERE code=?", (code,)).fetchone()
    return dict(row) if row else None


def pham_vi_ban(conn: sqlite3.Connection, user: dict) -> set[str] | None:
    """None = toàn tenant; set = các ban được quản trị; rỗng = không quản ai."""
    if la_super(user):
        return None
    if user["role_code"] == ADMIN:
        rows = conn.execute(
            "SELECT department_id FROM admin_scopes WHERE user_id=?", (user["id"],)
        ).fetchall()
        if not rows:
            # Không khai báo scope = chỉ ban của mình (mặc định đóng), không phải toàn tenant.
            return {user["department_id"]} if user.get("department_id") else set()
        if any(r["department_id"] is None for r in rows):
            return None
        return {r["department_id"] for r in rows}
    if user["role_code"] == MANAGER:
        return {user["department_id"]} if user.get("department_id") else set()
    return set()


def trong_pham_vi(conn: sqlite3.Connection, actor: dict, department_id: str | None) -> bool:
    scope = pham_vi_ban(conn, actor)
    if scope is None:
        return True
    if not department_id:
        return False
    return department_id in scope


def co_the_quan_ly(conn: sqlite3.Connection, actor: dict, perms: set[str], target: dict,
                   hanh_dong: str = "accounts.update") -> bool:
    """Luật chống leo thang cho mọi thao tác lên người khác."""
    if actor["id"] == target["id"]:
        return False
    if actor["tenant_id"] != target["tenant_id"]:
        return False
    if target["role_code"] == SUPER:
        return False
    if cap_vai_tro(conn, target["role_code"]) >= cap_vai_tro(conn, actor["role_code"]):
        return False
    if not co_quyen(actor, perms, hanh_dong):
        return False
    if actor["role_code"] in (ADMIN, MANAGER) and not trong_pham_vi(
            conn, actor, target.get("department_id")):
        return False
    return True


def kiem_tra_quan_ly(conn: sqlite3.Connection, actor: dict, perms: set[str], target: dict,
                     hanh_dong: str = "accounts.update") -> None:
    if not co_the_quan_ly(conn, actor, perms, target, hanh_dong):
        raise Forbidden("Bạn không được thao tác trên tài khoản này "
                        "(khác cấp, khác phạm vi hoặc thiếu quyền).")


def co_the_gan_vai_tro(conn: sqlite3.Connection, actor: dict, role_code: str) -> bool:
    if role_code == SUPER:
        return False
    return cap_vai_tro(conn, role_code) < cap_vai_tro(conn, actor["role_code"])


def kiem_tra_gan_vai_tro(conn: sqlite3.Connection, actor: dict, role_code: str) -> None:
    if not co_the_gan_vai_tro(conn, actor, role_code):
        raise Forbidden("Bạn chỉ được gán vai trò thấp hơn cấp của mình; "
                        "không thể tạo hoặc gán Super Admin.")


def co_the_cap_quyen(actor: dict, perms: set[str], quyen: str) -> bool:
    if actor["role_code"] == SUPER:
        return True
    if not co_quyen(actor, perms, "permissions.grant"):
        return False
    if quyen in QUYEN_CHI_SUPER:
        return False
    return quyen in perms


def kiem_tra_cap_quyen(actor: dict, perms: set[str], quyen: str) -> None:
    if not co_the_cap_quyen(actor, perms, quyen):
        raise Forbidden(f"Không thể cấp quyền '{quyen}': bạn chưa có quyền này "
                        "hoặc đây là quyền chỉ Super Admin.")


def kiem_tra_khong_tu_nang(actor: dict, target_id: str) -> None:
    if actor["id"] == target_id:
        raise Forbidden("Không thể tự thay đổi vai trò, quyền hoặc trạng thái của chính mình.")


def bao_ve_super_admin(target: dict) -> None:
    if target.get("role_code") == SUPER:
        raise Forbidden("Tài khoản Super Admin được bảo vệ: không ai được sửa, khoá hoặc xoá.")


def dem_super_admin(conn: sqlite3.Connection, tenant_id: str, tru: int = 0) -> int:
    n = conn.execute(
        "SELECT COUNT(*) FROM users WHERE tenant_id=? AND role_code=? AND status='active'",
        (tenant_id, SUPER)).fetchone()[0]
    return int(n) - tru


def kiem_tra_danh_sach_quyen(conn: sqlite3.Connection, perms: list[str]) -> list[str]:
    """Lọc mã quyền hợp lệ, trả danh sách đã chuẩn hoá (không trùng)."""
    if not perms:
        return []
    hop_le = {r["code"] for r in conn.execute("SELECT code FROM permissions").fetchall()}
    return sorted({p for p in perms if p in hop_le})


def mo_ta_quyen(conn: sqlite3.Connection, quyen: str) -> str:
    row = conn.execute("SELECT name FROM permissions WHERE code=?", (quyen,)).fetchone()
    return row["name"] if row else quyen


def kiem_tra_module_hop_le(conn: sqlite3.Connection, code: str) -> dict:
    m = module_theo_code(conn, code)
    if not m or m["status"] != "active":
        from .errors import NotFound
        raise NotFound("Module không tồn tại hoặc đã tắt.")
    return m


def co_module(user: dict, perms: set[str], code: str) -> bool:
    return la_super(user) or f"{code}.view" in perms
