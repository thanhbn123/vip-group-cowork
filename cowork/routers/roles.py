"""Quản lý vai trò và ma trận quyền."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import db, rbac, services, web
from ..errors import Forbidden, NotFound

router = APIRouter()


@router.get("/vai-tro")
async def danh_sach(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "roles.view"):
        raise Forbidden("Bạn không có quyền xem vai trò.")
    conn = db.connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM users u WHERE u.role_code=r.code "
            "AND u.status<>'archived') AS so_nguoi, "
            "(SELECT COUNT(*) FROM role_permissions rp WHERE rp.role_code=r.code) AS so_quyen "
            "FROM roles r ORDER BY r.level DESC").fetchall()]
        co_sua = rbac.co_quyen(user, request.state.perms, "roles.manage")
    finally:
        conn.close()
    return web.render(request, "roles/list.html", page_title="Vai trò", user=user, rows=rows,
                      co_sua=co_sua)


@router.get("/vai-tro/{role_code}")
async def chi_tiet(request: Request, role_code: str):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "roles.view"):
        raise Forbidden("Bạn không có quyền xem vai trò.")
    conn = db.connect()
    try:
        role = rbac.lay_vai_tro(conn, role_code)
        if not role:
            raise NotFound("Vai trò không tồn tại.")
        selected = {r["permission_code"] for r in conn.execute(
            "SELECT permission_code FROM role_permissions WHERE role_code=?",
            (role_code,)).fetchall()}
        modules = [dict(r) for r in conn.execute(
            "SELECT * FROM modules ORDER BY sort_order").fetchall()]
        perms = [dict(r) for r in conn.execute(
            "SELECT * FROM permissions ORDER BY module_code, action").fetchall()]
        theo_module = []
        for m in modules:
            ds = [p for p in perms if p["module_code"] == m["code"]]
            if ds:
                theo_module.append({"module": m, "perms": ds,
                                    "so_chon": sum(1 for p in ds if p["code"] in selected)})
        so_nguoi = conn.execute("SELECT COUNT(*) FROM users WHERE role_code=? AND status<>'archived'",
                                (role_code,)).fetchone()[0]
        co_sua = (rbac.co_quyen(user, request.state.perms, "roles.manage")
                  and role_code != rbac.SUPER and not role["is_locked"])
    finally:
        conn.close()
    return web.render(request, "roles/detail.html", page_title=f"Vai trò · {role['name']}",
                      user=user, role=role, theo_module=theo_module, selected=selected,
                      so_nguoi=int(so_nguoi), co_sua=co_sua)


@router.post("/vai-tro/{role_code}", dependencies=[Depends(web.kiem_csrf)])
async def cap_nhat(request: Request, role_code: str):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    quyen = form.getlist("quyen")
    conn = db.connect()
    try:
        try:
            services.cap_nhat_quyen_vai_tro(conn, user, request.state.perms, role_code, quyen,
                                             request)
        except (Forbidden, NotFound, ValueError) as e:
            return web.chuyen_huong(f"/vai-tro/{role_code}", getattr(e, "message", str(e)), "err")
    finally:
        conn.close()
    return web.chuyen_huong(f"/vai-tro/{role_code}", "Đã cập nhật quyền vai trò.")
