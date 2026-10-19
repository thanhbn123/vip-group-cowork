"""Đăng nhập / đăng xuất / đổi mật khẩu / hồ sơ và phiên cá nhân."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse

from .. import audit, auth, config, db, security, services, web
from ..errors import AuthRequired, Forbidden, ValidationError

router = APIRouter(dependencies=[Depends(web.nap_danh_tinh)])


@router.get("/dang-nhap")
async def trang_dang_nhap(request: Request, tiep: str = Query("/", alias="next")):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    resp = web.render(request, "login.html", page_title="Đăng nhập",
                      next_url=security.safe_next(tiep))
    if not request.cookies.get(config.CSRF_COOKIE):
        auth.dat_cookie_csrf(resp, request, request.state.csrf)
    return resp


@router.post("/dang-nhap", dependencies=[Depends(web.kiem_csrf)])
async def xu_ly_dang_nhap(request: Request, userId: str = Form(""),
                          matKhau: str = Form(""),
                          tiep: str = Form("/", alias="next")):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    ip = request.client.host if request.client else "?"
    conn = db.connect()
    try:
        try:
            user = auth.dang_nhap(conn, userId, matKhau, ip)
        except AuthRequired as e:
            tenant = config.TENANT_MAC_DINH
            row = conn.execute("SELECT tenant_id FROM users WHERE id=?",
                               (security.chuan_hoa_id(userId),)).fetchone()
            if row:
                tenant = row["tenant_id"]
            audit.ghi(conn, security.chuan_hoa_id(userId)[:40], "auth.login_fail",
                      detail={"lyDo": str(e)[:200], "ip": ip}, request=request, tenant_id=tenant)
            resp = web.chuyen_huong(
                f"/dang-nhap?next={security.safe_next(tiep)}",
                getattr(e, "message", "Sai ID hoặc mật khẩu."), "err")
            return resp
        phien, token = auth.tao_phien(conn, user, request)
        audit.ghi(conn, user, "auth.login", target_type="session", target_id=phien["id"],
                  detail={"ip": ip}, request=request)
        conn.commit()
        url = "/doi-mat-khau" if user.get("must_change_password") else security.safe_next(tiep)
        resp = RedirectResponse(url, status_code=303)
        auth.dat_cookie(resp, request, token)
        return resp
    finally:
        conn.close()


@router.post("/dang-xuat", dependencies=[Depends(web.kiem_csrf)])
async def dang_xuat(request: Request):
    user = request.state.user
    session = request.state.session
    if user and session:
        conn = db.connect()
        try:
            auth.thu_hoi_phien(conn, session["id"], user["id"], "Người dùng đăng xuất")
            audit.ghi(conn, user, "auth.logout", target_type="session", target_id=session["id"],
                      request=request)
        finally:
            conn.close()
    resp = RedirectResponse("/dang-nhap", status_code=303)
    auth.xoa_cookie(resp, request)
    web.set_flash(resp, "Đã đăng xuất an toàn.", "ok")
    return resp


@router.get("/doi-mat-khau")
async def trang_doi_mat_khau(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    return web.render(request, "change_password.html", page_title="Đổi mật khẩu", user=user)


@router.post("/doi-mat-khau", dependencies=[Depends(web.kiem_csrf)])
async def xu_ly_doi_mat_khau(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    mat_khau_cu = (form.get("matKhauCu") or "").strip()
    mat_khau_moi = (form.get("matKhauMoi") or "").strip()
    nhap_lai = (form.get("nhapLai") or "").strip()
    if mat_khau_moi != nhap_lai:
        return web.chuyen_huong("/doi-mat-khau", "Hai lần nhập mật khẩu mới không khớp.", "err")
    conn = db.connect()
    try:
        try:
            services.doi_mat_khau(conn, user, mat_khau_cu, mat_khau_moi, request)
        except (ValidationError, Forbidden) as e:
            return web.chuyen_huong("/doi-mat-khau", e.message, "err")
        user_moi = auth.nguoi_dung_day_du(conn, user["id"])
        phien, token = auth.tao_phien(conn, user_moi, request)
    finally:
        conn.close()
    resp = RedirectResponse("/", status_code=303)
    auth.dat_cookie(resp, request, token)
    web.set_flash(resp, "Đã đổi mật khẩu. Các phiên cũ đã bị thu hồi.", "ok")
    return resp


@router.get("/ho-so")
async def trang_ho_so(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    conn = db.connect()
    try:
        sessions = [dict(r) for r in conn.execute(
            "SELECT id, created_at, last_seen_at, expires_at, ip, user_agent "
            "FROM sessions WHERE user_id=? AND status='active' ORDER BY created_at DESC",
            (user["id"],)).fetchall()]
        nhat_ky = audit.cua_user(conn, user["tenant_id"], user["id"], 10)
        so_module = len(request.state.modules)
    finally:
        conn.close()
    return web.render(request, "profile.html", page_title="Hồ sơ của tôi", user=user,
                      sessions=sessions, current_session=(request.state.session or {}).get("id"),
                      nhat_ky=nhat_ky, so_module=so_module)


@router.post("/ho-so", dependencies=[Depends(web.kiem_csrf)])
async def cap_nhat_ho_so(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    conn = db.connect()
    try:
        try:
            services.cap_nhat_ho_so(conn, user, dict(form), request)
        except ValidationError as e:
            return web.chuyen_huong("/ho-so", e.message, "err")
    finally:
        conn.close()
    return web.chuyen_huong("/ho-so", "Đã cập nhật hồ sơ.")


@router.post("/ho-so/phien/{session_id}/thu-hoi", dependencies=[Depends(web.kiem_csrf)])
async def thu_hoi_phien_ca_nhan(request: Request, session_id: str):
    user = await web.yeu_cau_dang_nhap(request)
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id=? AND user_id=?",
                           (session_id, user["id"])).fetchone()
        if not row:
            return web.chuyen_huong("/ho-so", "Không tìm thấy phiên của bạn.", "err")
        auth.thu_hoi_phien(conn, session_id, user["id"], "Người dùng thu hồi phiên")
        audit.ghi(conn, user, "auth.session_revoke", target_type="session", target_id=session_id,
                  request=request)
    finally:
        conn.close()
    if (request.state.session or {}).get("id") == session_id:
        resp = RedirectResponse("/dang-nhap", status_code=303)
        auth.xoa_cookie(resp, request)
        web.set_flash(resp, "Đã thu hồi phiên hiện tại. Hãy đăng nhập lại.", "ok")
        return resp
    return web.chuyen_huong("/ho-so", "Đã thu hồi phiên.")
