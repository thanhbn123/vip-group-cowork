"""Sổ kiểm toán append-only (trigger DB chặn UPDATE/DELETE)."""
from __future__ import annotations

import json
import sqlite3

from . import db


def _ip(request) -> str | None:
    if request is None:
        return None
    try:
        return request.client.host if request.client else None
    except Exception:  # noqa: BLE001 - audit không được làm hỏng nghiệp vụ
        return None


def _ua(request) -> str | None:
    if request is None:
        return None
    try:
        return (request.headers.get("user-agent") or "")[:400] or None
    except Exception:  # noqa: BLE001
        return None


def ghi(conn: sqlite3.Connection, actor, action: str, *,
        target_type: str | None = None, target_id: str | None = None,
        detail: dict | list | str | None = None, request=None,
        tenant_id: str | None = None) -> int:
    """Ghi một dòng audit. `actor` là dict người dùng hoặc chuỗi ID (hệ thống/CLI)."""
    if isinstance(actor, dict):
        actor_id = actor.get("id") or actor.get("user_id") or "system"
        actor_role = actor.get("role_code")
        tenant = actor.get("tenant_id") or tenant_id
    else:
        actor_id = str(actor or "system")
        actor_role = None
        tenant = tenant_id
    if not tenant:
        raise ValueError("audit.ghi: thiếu tenant_id")
    if detail is None:
        detail_txt = None
    elif isinstance(detail, str):
        detail_txt = detail[:4000]
    else:
        detail_txt = json.dumps(detail, ensure_ascii=False, default=str)[:4000]
    cur = conn.execute(
        "INSERT INTO audit_log(tenant_id, actor_id, actor_role, action, target_type, target_id, "
        "detail, ip, user_agent, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (tenant, actor_id, actor_role, action, target_type, target_id,
         detail_txt, _ip(request), _ua(request), db.now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def liet_ke(conn: sqlite3.Connection, tenant_id: str, *, actor: str = "", action: str = "",
            target: str = "", tu_ngay: str = "", den_ngay: str = "",
            page: int = 1, page_size: int = 30) -> dict:
    where = ["tenant_id=?"]
    params: list = [tenant_id]
    if actor:
        where.append("actor_id=?")
        params.append(actor)
    if action:
        where.append("action LIKE ?")
        params.append(f"%{action}%")
    if target:
        where.append("(target_id LIKE ? OR target_type LIKE ?)")
        params += [f"%{target}%", f"%{target}%"]
    if tu_ngay:
        where.append("created_at>=?")
        params.append(tu_ngay)
    if den_ngay:
        where.append("created_at<=?")
        params.append(den_ngay + "T23:59:59+07:00")
    sql_where = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM audit_log WHERE {sql_where}", params).fetchone()[0]
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    offset = (page - 1) * page_size
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM audit_log WHERE {sql_where} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, page_size, offset)).fetchall()]
    for r in rows:
        if r.get("detail"):
            try:
                r["detail_obj"] = json.loads(r["detail"])
            except (ValueError, TypeError):
                r["detail_obj"] = None
    return {
        "rows": rows, "total": int(total), "page": page, "page_size": page_size,
        "pages": max(1, (int(total) + page_size - 1) // page_size),
    }


def cua_user(conn: sqlite3.Connection, tenant_id: str, user_id: str, limit: int = 8) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM audit_log WHERE tenant_id=? AND actor_id=? ORDER BY id DESC LIMIT ?",
        (tenant_id, user_id, limit)).fetchall()]


def dem_hom_nay(conn: sqlite3.Connection, tenant_id: str) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE tenant_id=? AND created_at>=?",
        (tenant_id, db.today_iso())).fetchone()[0])
