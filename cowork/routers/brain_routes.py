"""Mở VIP AI Brain từ COWORK bằng ticket one-time."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .. import audit, brain, db, rbac, web
from ..errors import Forbidden

router = APIRouter()


@router.get("/brain")
async def trang_brain(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not (rbac.la_super(user) or "brain.view" in request.state.perms):
        raise Forbidden("Bạn không được cấp module VIP AI Brain.")
    conn = db.connect()
    try:
        suc_khoe = brain.kiem_tra_suc_khoe(conn)
        cfg = brain.cau_hinh(conn)
        nhat_ky = [dict(r) for r in conn.execute(
            "SELECT * FROM audit_log WHERE tenant_id=? AND actor_id=? AND action='brain.launch' "
            "ORDER BY id DESC LIMIT 8", (user["tenant_id"], user["id"])).fetchall()]
        co_use = rbac.co_quyen(user, request.state.perms, "brain.use")
        so_phien_cowork = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id=? AND status='active'", (user["id"],)
        ).fetchone()[0]
    finally:
        conn.close()
    return web.render(request, "brain/index.html", page_title="VIP AI Brain", user=user,
                      suc_khoe=suc_khoe, cfg=cfg, nhat_ky=nhat_ky, co_use=co_use,
                      so_phien_cowork=int(so_phien_cowork))


@router.post("/brain/mo", dependencies=[Depends(web.kiem_csrf)])
async def mo_brain(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not (rbac.la_super(user) or "brain.use" in request.state.perms):
        raise Forbidden("Bạn không được cấp quyền sử dụng VIP AI Brain.")
    conn = db.connect()
    try:
        suc_khoe = brain.kiem_tra_suc_khoe(conn)
        if not suc_khoe.get("ok"):
            return web.chuyen_huong("/brain", "Không kết nối được VIP AI Brain: "
                                    + suc_khoe.get("thongBao", "không rõ lỗi"), "err")
        ticket = brain.tao_ticket(conn, user, (request.state.session or {}).get("id"),
                                  request.client.host if request.client else None)
        audit.ghi(conn, user, "brain.launch", target_type="brain", target_id="ticket",
                  detail={"url": brain.cau_hinh(conn)["public_url"]}, request=request)
        cfg = brain.cau_hinh(conn)
    finally:
        conn.close()
    url = cfg["public_url"] + cfg["launch_path"] + "?" + urlencode({"ticket": ticket})
    return RedirectResponse(url, status_code=303)


@router.get("/brain/trang-thai")
async def trang_thai(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not (rbac.la_super(user) or "brain.view" in request.state.perms):
        raise Forbidden("Bạn không được cấp module VIP AI Brain.")
    conn = db.connect()
    try:
        kq = brain.kiem_tra_suc_khoe(conn)
    finally:
        conn.close()
    return JSONResponse({"ok": bool(kq.get("ok")), "data": kq})
