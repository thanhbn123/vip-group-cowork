"""COWORK ↔ VIP AI BRAIN — cầu nối danh tính (bản vá THÊM, có cờ tắt).

Nguyên tắc:
- KHÔNG thay đổi cơ chế đăng nhập/MFA hiện có của Brain. Bridge chỉ THÊM hai cửa:
    GET  /cowork/vao              — đổi ticket COWORK lấy phiên Brain native
    POST /api/cowork/thu-hoi      — COWORK thu hồi phiên Brain (HMAC)
    GET  /api/cowork/suc-khoe     — chẩn đoán bridge (không lộ bí mật)
- Mặc định TẮT (`COWORK_BRIDGE_BAT=0`). Khi tắt, mọi cửa trả 404.
- Ticket do COWORK phát, dùng một lần, hết hạn 60 giây. Bridge gọi COWORK
  `/api/internal/brain/consume` bằng HMAC để đổi ticket; không tin dữ liệu trên URL.
- Tài khoản Brain được tạo "shadow" (không mật khẩu) nếu chưa có; KHÔNG đổi vai trò
  của tài khoản đã tồn tại. `anh-thanh` giữ nguyên `chu-so-huu`.
- Tài khoản đang bật MFA trên Brain KHÔNG được bridge bỏ qua, trừ khi
  `COWORK_BRIDGE_ALLOW_MFA_USERS=1` do chủ dự án bật sau nghiệm thu.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import cau_hinh
from ..store import audit_repo, db, sessions_repo

router = APIRouter()

TEN_COOKIE = "vip_session"  # trùng app/api/phu_thuoc.TEN_COOKIE
GIOI_HAN_BODY = 10_000


def _bat() -> bool:
    return os.environ.get("COWORK_BRIDGE_BAT", "0").strip() == "1"


def _bi_mat() -> str:
    return os.environ.get("COWORK_SHARED_SECRET", "").strip()


def _cookie_secure() -> bool:
    return os.environ.get("COWORK_BRIDGE_COOKIE_SECURE", "0").strip() == "1"


def _cho_mfa() -> bool:
    return os.environ.get("COWORK_BRIDGE_ALLOW_MFA_USERS", "0").strip() == "1"


def _cowork_url() -> str:
    return os.environ.get("COWORK_INTERNAL_URL", "http://127.0.0.1:8899").rstrip("/")


def _ky(direction: str, body: bytes) -> dict:
    ts = str(int(time.time()))
    sig = hmac.new(_bi_mat().encode("utf-8"),
                   f"{direction}.{ts}.".encode("utf-8") + body,
                   hashlib.sha256).hexdigest()
    return {"X-Cowork-Ts": ts, "X-Cowork-Sig": sig, "Content-Type": "application/json"}


def _xac_thuc(direction: str, request: Request, body: bytes) -> bool:
    if not _bi_mat():
        return False
    ts = request.headers.get("x-cowork-ts", "")
    sig = request.headers.get("x-cowork-sig", "")
    try:
        if abs(time.time() - int(ts)) > 300:
            return False
    except (TypeError, ValueError):
        return False
    mong = hmac.new(_bi_mat().encode("utf-8"),
                    f"{direction}.{ts}.".encode("utf-8") + body,
                    hashlib.sha256).hexdigest()
    return hmac.compare_digest(mong, sig)


def _json(status: int, ok: bool, data=None, ma: str = "", thong_bao: str = "") -> JSONResponse:
    if ok:
        return JSONResponse(status_code=status, content={"ok": True, "data": data})
    return JSONResponse(status_code=status,
                        content={"ok": False, "loi": {"ma": ma, "thongBao": thong_bao}})


def _trang_loi(status: int, tieu_de: str, thong_bao: str) -> HTMLResponse:
    """Trang lỗi tối giản, không template — bridge không phụ thuộc frontend Brain."""
    body = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(tieu_de)} · VIP AI BRAIN</title>
<style>
:root{{color-scheme:light}}body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
background:#f3f5f9;color:#0f2138;display:grid;place-items:center;min-height:100vh}}
.box{{background:#fff;border:1px solid #e3e8ef;border-radius:18px;max-width:520px;margin:20px;padding:30px;
box-shadow:0 24px 60px -24px rgba(15,33,56,.35)}}h1{{font-size:22px;margin:0 0 8px}}
p{{color:#64748b;line-height:1.6}}a{{display:inline-block;margin-top:14px;background:#0d2742;color:#fff;
text-decoration:none;padding:10px 16px;border-radius:10px;font-weight:600}}code{{background:#f1f4f8;padding:2px 6px;border-radius:6px}}
</style></head><body><main class="box"><h1>{html.escape(tieu_de)}</h1>
<p>{html.escape(thong_bao)}</p><a href="https://cowork.vipgroup.com.vn/">Về COWORK</a>
<p><small>Mã lỗi: {status} · Bridge COWORK</small></p></main></body></html>"""
    return HTMLResponse(status_code=status, content=body)


def _tenant_ton_tai(conn, tenant_id: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM tenants WHERE id=?", (tenant_id,)).fetchone())


def _vai_tro_brain(user_id: str, vai_tro_cowork: str) -> str:
    """Ánh xạ vai trò COWORK → Brain, FAIL-CLOSED theo phạm vi quyền.

    Chỉ `super_admin` của COWORK mới được map sang vai trò quản trị Brain. `admin` và
    `department_manager` của COWORK có phạm vi hẹp hơn (theo ban / tenant), trong khi
    vai trò `quan-tri` của Brain mở settings/audit/providers — map thẳng sẽ nâng quyền
    vượt phạm vi COWORK. Mọi vai trò còn lại (admin, department_manager, employee,
    partner) đều hạ xuống `thanh-vien`. Nếu sau này cần uỷ quyền Brain admin, phải làm
    thành cấu hình riêng có kiểm soát, không nới hàm này.
    """
    if vai_tro_cowork == "super_admin" and user_id == "anh-thanh":
        return "chu-so-huu"
    if vai_tro_cowork == "super_admin":
        return "quan-tri"
    return "thanh-vien"


def _dam_bao_quyen_chat_chung(conn, user_id: str, tenant_id: str, vai_tro_brain: str,
                              *, moi_tao: bool = False) -> None:
    """Cấp quyền ĐỌC dự án `tong-hop` cho shadow user của COWORK.

    Đây là quyền tối thiểu để một nhân viên COWORK dùng được cửa chat chung của Brain:
    `api/chat.py` chặn vai `thanh-vien` nếu không thấy `duAnId` (mặc định `tong-hop`).
    Quyền chỉ là `doc` trên ĐÚNG dự án chung `tong-hop` — KHÔNG cấp quyền dữ liệu của
    các dự án khác (kế toán, hải quan, logistics…). INSERT OR IGNORE để không ghi đè
    quyền đã có.

    Với user ĐÃ TỒN TẠI (`moi_tao=False`), chỉ backfill khi hội đủ dấu hiệu shadow cũ:
    không có mật khẩu Brain VÀ chưa có bất kỳ dòng `project_permissions` nào. Tài khoản
    native có mật khẩu, hoặc đã có quyền dự án, KHÔNG bị chạm — tránh mở rộng quyền
    ngoài phạm vi chỉ vì một ticket COWORK trùng id.
    """
    if vai_tro_brain != "thanh-vien":
        return  # quản trị Brain đã thấy mọi dự án (duAnIds=None)
    if not moi_tao:
        row = conn.execute("SELECT matKhauHash, salt FROM users WHERE id=?", (user_id,)).fetchone()
        if row and ((row["matKhauHash"] not in (None, b"", "")) or
                    (row["salt"] not in (None, b"", ""))):
            return  # tài khoản native có mật khẩu — không đụng
        if conn.execute(
                "SELECT 1 FROM project_permissions WHERE tenantId=? AND userId=? LIMIT 1",
                (tenant_id, user_id)).fetchone():
            return  # đã có quyền dự án (kể cả hẹp) — không tự mở thêm
    conn.execute(
        "INSERT OR IGNORE INTO project_permissions(tenantId, userId, duAnId, quyen) "
        "VALUES(?,?, 'tong-hop', 'doc')",
        (tenant_id, user_id),
    )


def _dam_bao_nguoi_dung(conn, user: dict, tenant_id: str) -> tuple[bool, str]:
    """Tạo shadow user nếu chưa có; KHÔNG sửa vai trò user đã tồn tại. Trả (ok, lý do)."""
    user_id = user.get("id", "")
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if row:
        if row["tenantId"] != tenant_id:
            return False, "Tài khoản Brain thuộc tenant khác — từ chối."
        if (row["trangThai"] or "") != "hoat-dong":
            return False, "Tài khoản Brain đang bị khoá — từ chối."
        # Shadow cũ do bridge trước đây tạo có thể chưa có quyền chat chung; backfill
        # có điều kiện (xem docstring) để user không phải bị xoá/tạo lại.
        _dam_bao_quyen_chat_chung(conn, user_id, tenant_id,
                                  row["vaiTro"] or "thanh-vien", moi_tao=False)
        conn.commit()
        return True, ""
    if not _tenant_ton_tai(conn, tenant_id):
        return False, "Tenant chưa tồn tại trong VIP AI BRAIN — từ chối."
    vai_tro_brain = _vai_tro_brain(user_id, user.get("vaiTro") or "employee")
    conn.execute(
        "INSERT INTO users(id, tenantId, ten, vaiTro, taoLuc, trangThai) VALUES(?,?,?,?,?, 'hoat-dong')",
        (user_id, tenant_id, user.get("ten") or user_id, vai_tro_brain, cau_hinh.gio_vn()),
    )
    _dam_bao_quyen_chat_chung(conn, user_id, tenant_id, vai_tro_brain, moi_tao=True)
    conn.commit()
    return True, ""


@router.get("/cowork/vao")
def vao(request: Request, ticket: str = ""):
    if not _bat():
        return _trang_loi(404, "Cầu nối COWORK đang tắt",
                          "Quản trị chưa bật COWORK_BRIDGE_BAT trên máy chủ này.")
    if not _bi_mat():
        return _trang_loi(503, "Thiếu cấu hình chia sẻ",
                          "COWORK_SHARED_SECRET chưa được cấu hình — từ chối (fail-closed).")
    ticket = (ticket or "").strip()
    if not ticket or len(ticket) > 200:
        return _trang_loi(400, "Thiếu ticket", "Hãy mở lại từ COWORK.")
    body = json.dumps({"ticket": ticket}).encode("utf-8")
    try:
        with httpx.Client(timeout=6) as client:
            r = client.post(_cowork_url() + "/api/internal/brain/consume",
                            content=body, headers=_ky("brain->cowork", body))
    except httpx.HTTPError:
        return _trang_loi(502, "Không gọi được COWORK",
                          "Máy chủ COWORK không phản hồi — từ chối tạo phiên (fail-closed).")
    if r.status_code != 200:
        return _trang_loi(401, "Ticket không hợp lệ",
                          "Ticket đã dùng, hết hạn hoặc quyền đã bị thu hồi. Hãy mở lại từ COWORK.")
    try:
        data = (r.json() or {}).get("data") or {}
        user = data.get("user") or {}
        quyen = data.get("quyen") or []
        tenant_id = (data.get("tenantId") or user.get("tenantId") or "").strip()
        user_id = (user.get("id") or "").strip()
    except (ValueError, TypeError):
        return _trang_loi(502, "Phản hồi COWORK không hợp lệ", "Thử lại từ COWORK.")
    if not user_id or not tenant_id or "brain.use" not in quyen or "brain.view" not in quyen:
        return _trang_loi(403, "Không đủ quyền",
                          "COWORK không cấp quyền module VIP AI Brain cho tài khoản này.")
    # MFA: KHÔNG bỏ qua cho tài khoản đang bật MFA, trừ khi chủ dự án bật cờ.
    bo_qua_mfa = False
    if cau_hinh.mfa_bat() and user_id == cau_hinh.mfa_user_id():
        if not _cho_mfa():
            conn = db.ket_noi()
            try:
                audit_repo.ghi(conn, user_id, "COWORK: Chặn mở phiên (MFA)",
                               f"tenant={tenant_id} — cần nghiệm thu COWORK trước",
                               tenant_id=tenant_id)
            finally:
                conn.close()
            return _trang_loi(403, "Chưa bỏ MFA cho tài khoản này",
                              "Theo quyết định của chủ dự án, tài khoản đang bật MFA của VIP AI Brain "
                              "chưa được mở qua COWORK cho tới khi cơ chế COWORK được nghiệm thu an toàn.")
        bo_qua_mfa = True

    conn = db.ket_noi()
    try:
        ok, ly_do = _dam_bao_nguoi_dung(conn, user, tenant_id)
        if not ok:
            audit_repo.ghi(conn, user_id, "COWORK: Từ chối mở phiên", ly_do, tenant_id=tenant_id)
            return _trang_loi(403, "Không thể mở phiên Brain", ly_do)
        try:
            phien = sessions_repo.tao(conn, user_id, tenant_id,
                                      request.client.host if request.client else "?")
        except Exception as e:  # noqa: BLE001 — không để bridge làm sập app
            return _trang_loi(500, "Không tạo được phiên Brain", f"Lỗi: {e.__class__.__name__}")
        audit_repo.ghi(
            conn, user_id, "COWORK: Mở phiên",
            f"tenant={tenant_id} vaiTro={user.get('vaiTro')} mfaBoQua={str(bo_qua_mfa).lower()}",
            tenant_id=tenant_id)
    finally:
        conn.close()

    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(TEN_COOKIE, phien["token"], httponly=True, samesite="lax", path="/",
                    secure=_cookie_secure(), max_age=sessions_repo.HAN_GIO * 3600)
    return resp


@router.post("/api/cowork/thu-hoi")
async def thu_hoi(request: Request):
    if not _bat():
        return _json(404, False, ma="BRIDGE_TAT", thong_bao="Bridge COWORK đang tắt.")
    raw = await request.body()
    if len(raw) > GIOI_HAN_BODY:
        return _json(413, False, ma="QUA_LON", thong_bao="Yêu cầu quá lớn.")
    if not _xac_thuc("cowork->brain", request, raw):
        return _json(401, False, ma="CHU_KY_SAI", thong_bao="Chữ ký không hợp lệ hoặc hết hạn.")
    try:
        body = json.loads(raw.decode("utf-8"))
        user_id = str((body or {}).get("userId") or "").strip()
        ly_do = str((body or {}).get("lyDo") or "COWORK thu hồi")[:300]
    except (ValueError, UnicodeDecodeError):
        return _json(400, False, ma="JSON_SAI", thong_bao="Body phải là JSON.")
    if not user_id:
        return _json(400, False, ma="THIEU_USER", thong_bao="Thiếu userId.")
    conn = db.ket_noi()
    try:
        cur = conn.execute(
            "UPDATE sessions SET trangThai='thu-hoi' WHERE userId=? AND trangThai='song'",
            (user_id,))
        conn.commit()
        n = int(cur.rowcount)
        audit_repo.ghi(conn, user_id, "COWORK: Thu hồi phiên",
                       f"{n} phiên — {ly_do}", tenant_id=None)
    finally:
        conn.close()
    return _json(200, True, data={"soPhien": n})


@router.get("/api/cowork/suc-khoe")
def suc_khoe():
    if not _bat():
        return _json(404, False, ma="BRIDGE_TAT", thong_bao="Bridge COWORK đang tắt.")
    return _json(200, True, data={
        "bridge": "bat",
        "cookieSecure": _cookie_secure(),
        "choMfa": _cho_mfa(),
        "coBiMat": bool(_bi_mat()),
    })
