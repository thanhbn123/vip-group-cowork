"""Fixture kiểm thử COWORK — DB tạm, không đụng dữ liệu thật."""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="cowork-pytest-")
os.environ["COWORK_DATA_DIR"] = TMP
os.environ["COWORK_DB_PATH"] = str(Path(TMP) / "cowork.db")
os.environ["COWORK_BRAIN_ENABLED"] = "0"
os.environ["COWORK_SECRET_KEY"] = "test-secret-key-khong-dung-production"
os.environ["COWORK_BRAIN_SHARED_SECRET"] = "test-brain-secret"
os.environ["COWORK_COOKIE_SECURE"] = "0"
os.environ["COWORK_ENV"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from cowork import auth, config, db, rbac, security, services  # noqa: E402
from cowork.main import app  # noqa: E402


def _xoa_db() -> None:
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(config.DB_PATH) + suffix)
        if p.exists():
            p.unlink()
    db._initialized = False
    db.init_db()


@pytest.fixture()
def client():
    _xoa_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def owner(client):
    conn = db.connect()
    try:
        services.tao_super_admin(conn, "anh-thanh", "Owner!Passw0rd", "anh-thanh")
        return auth.nguoi_dung_day_du(conn, "anh-thanh")
    finally:
        conn.close()


def csrf_tu(html: str) -> str:
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    assert m, "Không thấy CSRF trong HTML"
    return m.group(1)


def dang_nhap(client: TestClient, user_id: str, mat_khau: str, follow: bool = False):
    r = client.get("/dang-nhap")
    token = csrf_tu(r.text)
    return client.post("/dang-nhap", data={
        "userId": user_id, "matKhau": mat_khau, "_csrf": token, "next": "/",
    }, follow_redirects=follow)


def tao_user(role: str, user_id: str, mat_khau: str = "User!Passw0rd",
             dept: str | None = None, tenant: str = "vip-group",
             scope_mode: str = "tenant", scope_departments: list[str] | None = None,
             actor_id: str = "anh-thanh") -> dict:
    conn = db.connect()
    try:
        actor = auth.nguoi_dung_day_du(conn, actor_id)
        perms = rbac.quyen_hieu_luc(conn, actor)
        data = {
            "id": user_id, "display_name": user_id, "email": f"{user_id}@test.local",
            "role_code": role, "department_id": dept or "", "password": mat_khau,
            "must_change": "0", "scope_mode": scope_mode,
            "scope_departments": scope_departments or [],
            "partner_org": "Doi tac test" if role == "partner" else "",
        }
        user, _ = services.tao_nguoi_dung(conn, actor, perms, data)
        return user
    finally:
        conn.close()


def csrf_cua(client: TestClient) -> str:
    r = client.get("/ho-so")
    return csrf_tu(r.text)
