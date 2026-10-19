"""Nhật ký quản trị: xem, lọc, xuất CSV."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from .. import audit, db, rbac, web
from ..errors import Forbidden

router = APIRouter()


def _loc(request: Request):
    return {
        "actor": request.query_params.get("actor", "").strip()[:60],
        "action": request.query_params.get("action", "").strip()[:80],
        "target": request.query_params.get("target", "").strip()[:80],
        "tu_ngay": request.query_params.get("tu_ngay", "").strip()[:10],
        "den_ngay": request.query_params.get("den_ngay", "").strip()[:10],
    }


@router.get("/nhat-ky")
async def danh_sach(request: Request, page: int = Query(1, ge=1)):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "audit.view"):
        raise Forbidden("Bạn không có quyền xem nhật ký.")
    loc = _loc(request)
    conn = db.connect()
    try:
        kq = audit.liet_ke(conn, user["tenant_id"], page=page, page_size=30, **loc)
        ds_nguoi = [dict(r) for r in conn.execute(
            "SELECT DISTINCT actor_id FROM audit_log WHERE tenant_id=? ORDER BY actor_id LIMIT 100",
            (user["tenant_id"],)).fetchall()]
    finally:
        conn.close()
    return web.render(request, "audit/list.html", page_title="Nhật ký quản trị", user=user,
                      kq=kq, loc=loc, ds_nguoi=[r["actor_id"] for r in ds_nguoi])


@router.get("/nhat-ky/xuat.csv")
async def xuat_csv(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "audit.view"):
        raise Forbidden("Bạn không có quyền xuất nhật ký.")
    loc = _loc(request)
    conn = db.connect()
    try:
        kq = audit.liet_ke(conn, user["tenant_id"], page=1, page_size=5000, **loc)
    finally:
        conn.close()
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["id", "luc", "nguoi", "vaiTro", "hanhDong", "loaiDoiTuong", "doiTuong",
                "chiTiet", "ip"])
    for r in kq["rows"]:
        w.writerow([r["id"], r["created_at"], r["actor_id"], r["actor_role"] or "",
                    r["action"], r["target_type"] or "", r["target_id"] or "",
                    r["detail"] or "", r["ip"] or ""])
    data = buf.getvalue().encode("utf-8")
    return Response(data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="cowork-audit.csv"'})
