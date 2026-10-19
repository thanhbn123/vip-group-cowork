"""Đăng nhập / đăng xuất / đổi mật khẩu / hồ sơ và phiên cá nhân."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse

from .. import audit, auth, brain, config, db, security, services, web
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
    ip = web.ip_cua(request)
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
        # MFA: mật khẩu đúng CHƯA đủ để tạo phiên. Phát challenge 5 phút.
        if user.get("mfa_enabled"):
            if not user.get("mfa_secret"):
                audit.ghi(conn, user, "auth.mfa_fail", detail={"lyDo": "thieu_secret"},
                          request=request)
                return web.chuyen_huong("/dang-nhap", "MFA đang bật nhưng chưa cấu hình — "
                                                      "liên hệ quản trị (fail-closed).", "err")
            thach = auth.tao_thach_thuc_mfa(conn, user, request)
            audit.ghi(conn, user, "auth.mfa_challenge", target_type="mfa",
                      detail={"ip": ip, "hetHan": thach["expires_at"]}, request=request)
            resp = RedirectResponse(
                f"/dang-nhap/mfa?next={quote(security.safe_next(tiep))}", status_code=303)
            resp.set_cookie(auth.TEN_COOKIE_MFA, thach["token"],
                            **auth.cookie_kwargs(request, auth.MFA_PHUT * 60))
            return resp
        phien, token = auth.tao_phien(conn, user, request, ip=web.ip_cua(request))
        audit.ghi(conn, user, "auth.login", target_type="session", target_id=phien["id"],
                  detail={"ip": ip}, request=request)
        conn.commit()
        url = "/doi-mat-khau" if user.get("must_change_password") else security.safe_next(tiep)
        resp = RedirectResponse(url, status_code=303)
        auth.dat_cookie(resp, request, token)
        return resp
    finally:
        conn.close()


@router.get("/dang-nhap/mfa")
async def trang_mfa(request: Request, tiep: str = Query("/", alias="next")):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    if not request.cookies.get(auth.TEN_COOKIE_MFA):
        return web.chuyen_huong("/dang-nhap", "Phiên xác thực 2 lớp không còn — đăng nhập lại.", "err")
    resp = web.render(request, "login_mfa.html", page_title="Xác thực 2 lớp",
                      next_url=security.safe_next(tiep))
    if not request.cookies.get(config.CSRF_COOKIE):
        auth.dat_cookie_csrf(resp, request, request.state.csrf)
    return resp


@router.post("/dang-nhap/mfa", dependencies=[Depends(web.kiem_csrf)])
async def xu_ly_mfa(request: Request, ma: str = Form(""),
                    tiep: str = Form("/", alias="next")):
    token = request.cookies.get(auth.TEN_COOKIE_MFA)
    conn = db.connect()
    try:
        user = auth.xac_thuc_mfa(conn, token, ma)
        if not user:
            return web.chuyen_huong(
                f"/dang-nhap/mfa?next={quote(security.safe_next(tiep))}",
                "Mã xác thực không đúng, đã dùng hoặc đã hết hạn. Thử mã mới/mã dự phòng.", "err")
        phien, token_phien = auth.tao_phien(conn, user, request, ip=web.ip_cua(request))
        audit.ghi(conn, user, "auth.mfa_ok", target_type="session", target_id=phien["id"],
                  detail={"ip": web.ip_cua(request)}, request=request)
        conn.commit()
        url = "/doi-mat-khau" if user.get("must_change_password") else security.safe_next(tiep)
        resp = RedirectResponse(url, status_code=303)
        auth.dat_cookie(resp, request, token_phien)
        resp.delete_cookie(auth.TEN_COOKIE_MFA, path="/")
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
            # Đăng xuất COWORK cũng thu hồi phiên Brain native của cùng danh tính (nếu có).
            kq_brain = {"ok": None}
            if "brain.view" in getattr(request.state, "perms", set()):
                kq_brain = brain.thu_hoi_phien(conn, user["id"], "COWORK đăng xuất")
            audit.ghi(conn, user, "auth.logout", target_type="session", target_id=session["id"],
                      detail={"brainRevoke": kq_brain.get("ok")},
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
        phien, token = auth.tao_phien(conn, user_moi, request, ip=web.ip_cua(request))
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


# ------------------------------- MFA cá nhân -------------------------------
@router.get("/ho-so/mfa")
async def trang_mfa_ca_nhan(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    conn = db.connect()
    try:
        user = auth.nguoi_dung_day_du(conn, user["id"])
        if user.get("mfa_enabled"):
            con_lai = auth.ma_du_phong_con_lai(conn, user["id"])
            return web.render(request, "mfa_manage.html", page_title="Xác thực 2 lớp",
                              user=user, con_lai=con_lai)
        secret = security.tao_bi_mat_totp()
        uri = security.otpauth_uri(secret, user["id"])
        return web.render(request, "mfa_setup.html", page_title="Bật xác thực 2 lớp",
                          user=user, secret=secret, uri=uri)
    finally:
        conn.close()


@router.post("/ho-so/mfa/bat", dependencies=[Depends(web.kiem_csrf)])
async def bat_mfa(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    conn = db.connect()
    try:
        try:
            codes = auth.bat_mfa(conn, user, (form.get("secret") or "").strip(),
                                 (form.get("ma") or "").strip(),
                                 (form.get("matKhau") or "").strip())
        except ValidationError as e:
            return web.chuyen_huong("/ho-so/mfa", e.message, "err")
        audit.ghi(conn, user, "mfa.enable", target_type="user", target_id=user["id"],
                  detail={"soMaDuPhong": len(codes)}, request=request)
        user = auth.nguoi_dung_day_du(conn, user["id"])
    finally:
        conn.close()
    return web.render(request, "mfa_codes.html", page_title="Mã dự phòng MFA",
                      user=user, codes=codes, che_do="bat")


@router.post("/ho-so/mfa/tat", dependencies=[Depends(web.kiem_csrf)])
async def tat_mfa(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    conn = db.connect()
    try:
        try:
            auth.tat_mfa(conn, user, (form.get("matKhau") or "").strip(),
                         (form.get("ma") or "").strip())
        except ValidationError as e:
            return web.chuyen_huong("/ho-so/mfa", e.message, "err")
        audit.ghi(conn, user, "mfa.disable", target_type="user", target_id=user["id"],
                  request=request)
    finally:
        conn.close()
    return web.chuyen_huong("/ho-so/mfa", "Đã tắt xác thực 2 lớp.")


@router.post("/ho-so/mfa/ma-du-phong", dependencies=[Depends(web.kiem_csrf)])
async def tao_lai_ma_du_phong(request: Request):
    user = await web.yeu_cau_dang_nhap(request)
    form = await request.form()
    conn = db.connect()
    try:
        try:
            codes = auth.tao_lai_ma_du_phong(conn, user, (form.get("matKhau") or "").strip(),
                                             (form.get("ma") or "").strip())
        except ValidationError as e:
            return web.chuyen_huong("/ho-so/mfa", e.message, "err")
        audit.ghi(conn, user, "mfa.backup_codes", target_type="user", target_id=user["id"],
                  detail={"soMa": len(codes)}, request=request)
        user = auth.nguoi_dung_day_du(conn, user["id"])
    finally:
        conn.close()
    return web.render(request, "mfa_codes.html", page_title="Mã dự phòng mới",
                      user=user, codes=codes, che_do="tao_lai")
