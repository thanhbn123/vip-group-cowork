"""API nội bộ cho VIP AI BRAIN — xác thực HMAC, không dùng cookie/CSRF."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import audit, brain, db, security

router = APIRouter()


def _loi(status: int, ma: str, thong_bao: str) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content={"ok": False, "loi": {"ma": ma, "thongBao": thong_bao}})


@router.post("/api/internal/brain/consume")
async def consume(request: Request):
    raw = await request.body()
    if len(raw) > 10_000:
        return _loi(413, "QUA_LON", "Yêu cầu quá lớn.")
    if not security.xac_thuc_hmac(
            "brain->cowork", request.headers.get("x-cowork-ts"),
            request.headers.get("x-cowork-sig"), raw):
        return _loi(401, "CHU_KY_SAI", "Chữ ký nội bộ không hợp lệ hoặc đã hết hạn.")
    try:
        body = json.loads(raw.decode("utf-8"))
        ticket = str((body or {}).get("ticket") or "").strip()
    except (ValueError, UnicodeDecodeError):
        return _loi(400, "JSON_SAI", "Body phải là JSON.")
    conn = db.connect()
    try:
        kq = brain.tieu_ticket(conn, ticket)
        if not kq:
            return _loi(401, "TICKET_KHONG_HOP_LE",
                        "Ticket không tồn tại, đã dùng, hết hạn hoặc quyền đã bị thu hồi.")
        actor = {"id": kq["user"]["id"], "role_code": kq["user"]["vaiTro"],
                 "tenant_id": kq["tenantId"]}
        audit.ghi(conn, actor, "brain.consume", target_type="brain", target_id="session",
                  detail={"ticketHash": security.sha256(ticket)[:16]}, request=request)
    finally:
        conn.close()
    kq["exp"] = db.now_iso()
    return JSONResponse({"ok": True, "data": kq})


@router.get("/api/internal/brain/ping")
async def ping():
    return JSONResponse({"ok": True, "data": {"app": "cowork", "lop": "internal"}})
