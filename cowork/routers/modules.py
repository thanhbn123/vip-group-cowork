"""Module registry: bật/tắt, mô tả, thứ tự hiển thị."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import audit, db, rbac, services, web
from ..errors import Forbidden, NotFound

router = APIRouter()


@router.get("/module-registry")
async def danh_sach(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "modules.view"):
        raise Forbidden("Bạn không có quyền xem module registry.")
    conn = db.connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT m.*, (SELECT COUNT(*) FROM permissions p WHERE p.module_code=m.code) "
            "AS so_quyen FROM modules m ORDER BY m.sort_order").fetchall()]
        co_sua = rbac.co_quyen(user, request.state.perms, "modules.manage")
    finally:
        conn.close()
    return web.render(request, "modules/list.html", page_title="Module", user=user, rows=rows,
                      co_sua=co_sua)


@router.post("/module-registry/{code}", dependencies=[Depends(web.kiem_csrf)])
async def cap_nhat(request: Request, code: str):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    conn = db.connect()
    try:
        module = rbac.module_theo_code(conn, code)
        if not module:
            raise NotFound("Module không tồn tại.")
        try:
            services.cap_nhat_module(conn, user, request.state.perms, module, dict(form), request)
        except Forbidden as e:
            return web.chuyen_huong("/module-registry", e.message, "err")
    finally:
        conn.close()
    return web.chuyen_huong("/module-registry", "Đã cập nhật module.")
