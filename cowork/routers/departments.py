"""Quản lý ban / bộ phận."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import db, rbac, services, web
from ..errors import Conflict, Forbidden, NotFound, ValidationError

router = APIRouter()


def _dept(conn, actor: dict, dept_id: str) -> dict:
    row = conn.execute("SELECT * FROM departments WHERE id=? AND tenant_id=?",
                       (dept_id, actor["tenant_id"])).fetchone()
    if not row:
        raise NotFound("Không tìm thấy ban/bộ phận trong tenant.")
    return dict(row)


@router.get("/ban")
async def danh_sach(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "departments.view"):
        raise Forbidden("Bạn không có quyền xem ban/bộ phận.")
    conn = db.connect()
    try:
        scope = rbac.pham_vi_ban(conn, user)
        rows = [dict(r) for r in conn.execute(
            "SELECT d.*, m.display_name AS manager_name, "
            "(SELECT COUNT(*) FROM users u WHERE u.department_id=d.id AND u.status<>'archived') "
            "AS so_nguoi FROM departments d LEFT JOIN users m ON m.id=d.manager_user_id "
            "WHERE d.tenant_id=? AND d.status='active' ORDER BY d.name",
            (user["tenant_id"],)).fetchall()]
        if scope is not None:
            rows = [r for r in rows if r["id"] in scope]
        co_tao = rbac.co_quyen(user, request.state.perms, "departments.create") and scope is None
        co_sua = rbac.co_quyen(user, request.state.perms, "departments.update")
    finally:
        conn.close()
    return web.render(request, "departments/list.html", page_title="Ban / Bộ phận", user=user,
                      rows=rows, co_tao=co_tao, co_sua=co_sua)


@router.get("/ban/tao-moi")
async def trang_tao(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "departments.create"):
        raise Forbidden("Bạn không có quyền tạo ban/bộ phận.")
    if rbac.pham_vi_ban(db.connect(), user) is not None:
        raise Forbidden("Chỉ quản trị toàn tenant mới được tạo ban mới.")
    return web.render(request, "departments/form.html", page_title="Tạo ban / bộ phận", user=user,
                      dept=None)


@router.post("/ban/tao-moi", dependencies=[Depends(web.kiem_csrf)])
async def xu_ly_tao(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    conn = db.connect()
    try:
        try:
            dept = services.tao_ban(conn, user, request.state.perms, dict(form), request)
        except (ValidationError, Conflict, Forbidden) as e:
            return web.render(request, "departments/form.html", page_title="Tạo ban / bộ phận",
                              user=user, dept=None, form=dict(form), error=e.message,
                              status_code=400)
    finally:
        conn.close()
    return web.chuyen_huong(f"/ban/{dept['id']}", "Đã tạo ban/bộ phận.")


@router.get("/ban/{dept_id}")
async def chi_tiet(request: Request, dept_id: str):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "departments.view"):
        raise Forbidden("Bạn không có quyền xem ban/bộ phận.")
    conn = db.connect()
    try:
        dept = _dept(conn, user, dept_id)
        if not rbac.trong_pham_vi(conn, user, dept_id):
            raise Forbidden("Ban này nằm ngoài phạm vi bạn được uỷ quyền.")
        dept = dict(conn.execute(
            "SELECT d.*, m.display_name AS manager_name FROM departments d "
            "LEFT JOIN users m ON m.id=d.manager_user_id WHERE d.id=?", (dept_id,)).fetchone())
        thanh_vien = [dict(r) for r in conn.execute(
            "SELECT u.*, r.name AS role_name, r.level AS role_level FROM users u "
            "JOIN roles r ON r.code=u.role_code WHERE u.department_id=? AND u.status<>'archived' "
            "ORDER BY r.level DESC, u.id", (dept_id,)).fetchall()]
        ung_vien = [dict(r) for r in conn.execute(
            "SELECT u.id, u.display_name, r.name AS role_name FROM users u "
            "JOIN roles r ON r.code=u.role_code WHERE u.tenant_id=? AND u.status='active' "
            "AND r.level>=? ORDER BY u.display_name",
            (user["tenant_id"], rbac.cap_vai_tro(conn, rbac.MANAGER))).fetchall()]
        co_sua = (rbac.co_quyen(user, request.state.perms, "departments.update")
                  and rbac.trong_pham_vi(conn, user, dept_id))
        co_luu_tru = (rbac.co_quyen(user, request.state.perms, "departments.delete")
                      and rbac.trong_pham_vi(conn, user, dept_id))
    finally:
        conn.close()
    return web.render(request, "departments/detail.html", page_title=f"Ban · {dept['name']}",
                      user=user, dept=dept, thanh_vien=thanh_vien, ung_vien=ung_vien,
                      co_sua=co_sua, co_luu_tru=co_luu_tru)


@router.post("/ban/{dept_id}", dependencies=[Depends(web.kiem_csrf)])
async def xu_ly_cap_nhat(request: Request, dept_id: str):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    conn = db.connect()
    try:
        dept = _dept(conn, user, dept_id)
        try:
            services.cap_nhat_ban(conn, user, request.state.perms, dept, dict(form), request)
        except (ValidationError, Forbidden, Conflict) as e:
            return web.chuyen_huong(f"/ban/{dept_id}", e.message, "err")
    finally:
        conn.close()
    return web.chuyen_huong(f"/ban/{dept_id}", "Đã cập nhật ban/bộ phận.")


@router.post("/ban/{dept_id}/luu-tru", dependencies=[Depends(web.kiem_csrf)])
async def luu_tru(request: Request, dept_id: str):
    user = await web.yeu_cau_dang_nhap(request)
    conn = db.connect()
    try:
        dept = _dept(conn, user, dept_id)
        try:
            services.luu_tru_ban(conn, user, request.state.perms, dept, request)
        except (Conflict, Forbidden) as e:
            return web.chuyen_huong(f"/ban/{dept_id}", e.message, "err")
    finally:
        conn.close()
    return web.chuyen_huong("/ban", "Đã lưu trữ ban/bộ phận.")
