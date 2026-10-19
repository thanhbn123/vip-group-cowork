"""Client gọi VIP AI BRAIN — chỉ HTTP, không đọc/ghi DB Brain."""
from __future__ import annotations

import json
import sqlite3

import httpx

from . import config, db, security


def cau_hinh(conn: sqlite3.Connection) -> dict:
    return db.brain_config(conn)


def kiem_tra_suc_khoe(conn: sqlite3.Connection) -> dict:
    cfg = cau_hinh(conn)
    if not cfg["enabled"]:
        return {"ok": False, "trangThai": "tat", "thongBao": "Module Brain đang tắt trong cài đặt."}
    try:
        with httpx.Client(timeout=config.BRAIN_TIMEOUT) as client:
            r = client.get(cfg["base_url"] + cfg["health_path"])
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "trangThai": "song", "http": r.status_code,
                    "duLieu": data.get("data", data), "url": cfg["base_url"]}
        return {"ok": False, "trangThai": "loi", "http": r.status_code,
                "thongBao": f"Brain trả HTTP {r.status_code}.", "url": cfg["base_url"]}
    except httpx.HTTPError as e:
        return {"ok": False, "trangThai": "khong-ket-noi", "thongBao": str(e)[:300],
                "url": cfg["base_url"]}


def thu_hoi_phien(conn: sqlite3.Connection, user_id: str, ly_do: str = "COWORK thu hồi quyền") -> dict:
    """Gọi Brain thu hồi toàn bộ phiên của một user (HMAC). Không ném lỗi ra nghiệp vụ."""
    cfg = cau_hinh(conn)
    if not cfg["enabled"]:
        return {"ok": False, "boQua": True, "thongBao": "Brain đang tắt."}
    body = json.dumps({"userId": user_id, "lyDo": ly_do[:300]}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", **security.ky_hmac("cowork->brain", body)}
    try:
        with httpx.Client(timeout=config.BRAIN_TIMEOUT) as client:
            r = client.post(cfg["base_url"] + cfg["revoke_path"], content=body, headers=headers)
        ok = r.status_code == 200
        return {"ok": ok, "http": r.status_code,
                "thongBao": "" if ok else f"Brain trả HTTP {r.status_code}: {r.text[:200]}"}
    except httpx.HTTPError as e:
        return {"ok": False, "thongBao": f"Không gọi được Brain: {str(e)[:200]}"}


def tao_ticket(conn: sqlite3.Connection, user: dict, session_id: str | None, ip: str | None) -> str:
    """Sinh ticket one-time; chỉ trả token thô, DB chỉ giữ hash."""
    token = security.token_moi(32)
    now = db.now_iso()
    conn.execute("DELETE FROM brain_tickets WHERE expires_at<?", (now,))
    from datetime import datetime, timedelta
    het_han = (datetime.now(db.TZ) + timedelta(seconds=config.BRAIN_TICKET_TTL)).replace(
        microsecond=0).isoformat()
    conn.execute(
        "INSERT INTO brain_tickets(id, ticket_hash, tenant_id, user_id, session_id, expires_at, "
        "created_at, ip) VALUES(?,?,?,?,?,?,?,?)",
        (security.token_moi(10), security.sha256(token), user["tenant_id"], user["id"],
         session_id, het_han, now, ip),
    )
    conn.commit()
    return token


def tieu_ticket(conn: sqlite3.Connection, token: str) -> dict | None:
    """Đổi ticket lấy danh tính + quyền. One-time, hết hạn 60 giây, kiểm lại trạng thái."""
    if not token or len(token) < 20:
        return None
    row = conn.execute(
        "SELECT * FROM brain_tickets WHERE ticket_hash=?", (security.sha256(token),)).fetchone()
    if not row:
        return None
    t = dict(row)
    if t["used_at"]:
        return None
    try:
        from datetime import datetime
        if datetime.now(db.TZ) >= datetime.fromisoformat(t["expires_at"]):
            return None
    except (TypeError, ValueError):
        return None
    cur = conn.execute("UPDATE brain_tickets SET used_at=? WHERE id=? AND used_at IS NULL",
                       (db.now_iso(), t["id"]))
    conn.commit()
    if cur.rowcount != 1:
        return None
    from . import auth, rbac
    user = auth.nguoi_dung_day_du(conn, t["user_id"])
    if not user or user["status"] != "active" or user["tenant_id"] != t["tenant_id"]:
        return None
    perms = rbac.quyen_hieu_luc(conn, user)
    modules = rbac.module_hien_thi(conn, user, perms)
    if not rbac.co_module(user, perms, "brain") or "brain.use" not in perms:
        return None
    return {
        "ok": True,
        "user": {
            "id": user["id"], "ten": user["display_name"], "vaiTro": user["role_code"],
            "tenVaiTro": user["role_name"], "tenantId": user["tenant_id"],
            "email": user.get("email"), "departmentId": user.get("department_id"),
        },
        "quyen": sorted(perms),
        "modules": [{"code": m["code"], "name": m["name"]} for m in modules],
        "tenantId": user["tenant_id"],
        "sessionId": t.get("session_id"),
    }
