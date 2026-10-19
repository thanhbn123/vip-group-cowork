"""Cài đặt tenant, bảo mật phiên và kết nối VIP AI Brain."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .. import audit, auth, brain, config, db, rbac, services, web
from ..errors import Forbidden

router = APIRouter()


CAI_DAT_HIEN = [
    ("tenant.display_name", "Tên tổ chức", "text"),
    ("security.session_hours", "Hạn phiên tối đa (giờ)", "number"),
    ("security.idle_minutes", "Tự đăng xuất sau (phút)", "number"),
    ("security.password_min", "Độ dài mật khẩu tối thiểu", "number"),
    ("brain.base_url", "URL nội bộ của Brain", "text"),
    ("brain.public_url", "URL công khai của Brain", "text"),
    ("branding.support_note", "Ghi chú hỗ trợ", "text"),
]


@router.get("/cai-dat")
async def trang_cai_dat(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "settings.view"):
        raise Forbidden("Bạn không có quyền xem cài đặt.")
    conn = db.connect()
    try:
        gia_tri = {k: db.get_setting(conn, k, "") for k, _, _ in CAI_DAT_HIEN}
        bat = db.get_setting(conn, "brain.enabled", "1")
        mfa = db.get_setting(conn, "brain.allow_mfa_users", "0")
        suc_khoe = brain.kiem_tra_suc_khoe(conn)
        so_phien = conn.execute("SELECT COUNT(*) FROM sessions WHERE tenant_id=? AND status='active'",
                                (user["tenant_id"],)).fetchone()[0]
        so_user = conn.execute("SELECT COUNT(*) FROM users WHERE tenant_id=? AND status<>'archived'",
                               (user["tenant_id"],)).fetchone()[0]
        nhat_ky = audit.liet_ke(conn, user["tenant_id"], action="settings.", page=1,
                                page_size=8)["rows"]
        co_sua = rbac.co_quyen(user, request.state.perms, "settings.manage")
    finally:
        conn.close()
    return web.render(request, "settings.html", page_title="Cài đặt", user=user,
                      gia_tri=gia_tri, brain_bat=bat, brain_mfa=mfa, suc_khoe=suc_khoe,
                      so_phien=int(so_phien), so_user=int(so_user), nhat_ky=nhat_ky,
                      co_sua=co_sua, cai_dat_hien=CAI_DAT_HIEN,
                      config_brain_base=config.BRAIN_BASE_URL,
                      config_brain_public=config.BRAIN_PUBLIC_URL,
                      brain_secret_set=bool(config.BRAIN_SHARED_SECRET))


@router.post("/cai-dat", dependencies=[Depends(web.kiem_csrf)])
async def luu_cai_dat(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    conn = db.connect()
    try:
        try:
            thay_doi = services.cap_nhat_cai_dat(conn, user, request.state.perms, dict(form), request)
        except (Forbidden, ValueError) as e:
            return web.chuyen_huong("/cai-dat", getattr(e, "message", str(e)), "err")
    finally:
        conn.close()
    return web.chuyen_huong("/cai-dat",
                            "Đã lưu cài đặt." if thay_doi else "Không có thay đổi.")


@router.get("/cai-dat/kiem-tra-brain")
async def kiem_tra_brain(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if not rbac.co_quyen(user, request.state.perms, "settings.view"):
        raise Forbidden("Bạn không có quyền kiểm tra Brain.")
    conn = db.connect()
    try:
        kq = brain.kiem_tra_suc_khoe(conn)
    finally:
        conn.close()
    return JSONResponse({"ok": bool(kq.get("ok")), "data": kq})


@router.post("/cai-dat/thu-hoi-toan-bo", dependencies=[Depends(web.kiem_csrf)])
async def thu_hoi_toan_bo(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    if user["role_code"] != rbac.SUPER:
        raise Forbidden("Chỉ Super Admin được thu hồi toàn bộ phiên.")
    hien_tai = (request.state.session or {}).get("id")
    conn = db.connect()
    try:
        cur = conn.execute(
            "UPDATE sessions SET status='revoked', revoked_at=?, revoked_by=?, "
            "revoke_reason='Super Admin thu hồi toàn bộ' WHERE tenant_id=? AND status='active' "
            "AND id<>?", (db.now_iso(), user["id"], user["tenant_id"], hien_tai or ""))
        conn.commit()
        n = int(cur.rowcount)
        audit.ghi(conn, user, "settings.revoke_all_sessions", target_type="tenant",
                  target_id=user["tenant_id"], detail={"soPhien": n}, request=request)
    finally:
        conn.close()
    return web.chuyen_huong("/cai-dat", f"Đã thu hồi {n} phiên (giữ phiên hiện tại).")
