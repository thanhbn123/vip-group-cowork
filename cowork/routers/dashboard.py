"""Dashboard theo vai trò, trang module, cổng đối tác và API công khai."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .. import audit, db, rbac, services, web
from ..errors import NotFound

router = APIRouter()


@router.get("/")
async def dashboard(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    conn = db.connect()
    try:
        tk = services.thong_ke(conn, user, request.state.perms)
        nhat_ky = audit.cua_user(conn, user["tenant_id"], user["id"], 8)
        gan_day = []
        if rbac.la_super(user) or "audit.view" in request.state.perms:
            gan_day = audit.liet_ke(conn, user["tenant_id"], page=1, page_size=8)["rows"]
        # Số người theo ban cho quản trị
        theo_ban = []
        if rbac.la_super(user) or "accounts.view" in request.state.perms:
            scope = rbac.pham_vi_ban(conn, user)
            rows = conn.execute(
                "SELECT d.id, d.name, COUNT(u.id) AS soNguoi FROM departments d "
                "LEFT JOIN users u ON u.department_id=d.id AND u.status<>'archived' "
                "WHERE d.tenant_id=? AND d.status='active' GROUP BY d.id ORDER BY d.name",
                (user["tenant_id"],)).fetchall()
            theo_ban = [dict(r) for r in rows if scope is None or r["id"] in scope]
        so_module = len(request.state.modules)
    finally:
        conn.close()
    return web.render(request, "dashboard.html", page_title="Bảng điều khiển", user=user,
                      tk=tk, nhat_ky=nhat_ky, gan_day=gan_day, theo_ban=theo_ban,
                      so_module=so_module)


@router.get("/module/{code}")
async def trang_module(request: Request, code: str):
    user = await web.yeu_cau_dang_nhap(request)
    conn = db.connect()
    try:
        m = rbac.module_theo_code(conn, code)
        if not m or m["status"] != "active":
            raise NotFound("Module không tồn tại hoặc đã tắt.")
        if not (rbac.la_super(user) or f"{code}.view" in request.state.perms):
            from ..errors import Forbidden
            raise Forbidden("Bạn không được cấp module này.")
        health = None
        if m["requires_brain"]:
            from .. import brain
            health = brain.kiem_tra_suc_khoe(conn)
    finally:
        conn.close()
    return web.render(request, "module.html", page_title=m["name"], user=user,
                      module=m, health=health)


@router.get("/doi-tac")
async def cong_doi_tac(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    conn = db.connect()
    try:
        if not (rbac.la_super(user) or "partner.view" in request.state.perms):
            from ..errors import Forbidden
            raise Forbidden("Bạn không có quyền truy cập cổng đối tác.")
        modules = [m for m in request.state.modules if m["group_code"] == "workspace"]
        nhat_ky = audit.cua_user(conn, user["tenant_id"], user["id"], 6)
    finally:
        conn.close()
    return web.render(request, "partner.html", page_title="Cổng đối tác", user=user,
                      modules=modules, nhat_ky=nhat_ky)


# ------------------------------- API công khai -------------------------------
@router.get("/api/health")
async def health(request: Request):
    conn = db.connect()
    try:
        db_ok = bool(conn.execute("SELECT 1").fetchone())
        brain_status = "tat"
        try:
            from .. import brain
            cfg = brain.cau_hinh(conn)
            if cfg["enabled"]:
                brain_status = "bat"
        except Exception:  # noqa: BLE001
            brain_status = "loi"
        return JSONResponse({
            "ok": True,
            "data": {"app": "cowork", "version": "1.0.0", "db": "ok" if db_ok else "loi",
                     "brain": brain_status, "gio": db.now_iso()},
        })
    finally:
        conn.close()


@router.get("/api/me")
async def api_me(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    return JSONResponse({
        "ok": True,
        "data": {
            "id": user["id"], "ten": user["display_name"], "vaiTro": user["role_code"],
            "tenVaiTro": user["role_name"], "tenantId": user["tenant_id"],
            "ban": user.get("department_name"),
            "modules": [m["code"] for m in request.state.modules],
            "quyen": sorted(request.state.perms),
        },
    })
