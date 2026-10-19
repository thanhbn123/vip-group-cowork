"""Kiểm thử MFA TOTP cho COWORK — DB tạm, không đụng dữ liệu thật."""
from __future__ import annotations

import pytest
from conftest import csrf_tu, dang_nhap, tao_user

from cowork import auth, cli, db, security
from cowork.errors import ValidationError


def _bat_mfa(user_id: str, mat_khau: str = "User!Passw0rd") -> tuple[str, list[str]]:
    conn = db.connect()
    try:
        user = auth.nguoi_dung_day_du(conn, user_id)
        secret = security.tao_bi_mat_totp()
        codes = auth.bat_mfa(conn, user, secret, security.totp(secret), mat_khau)
        return secret, codes
    finally:
        conn.close()


def test_totp_dung_va_cua_so():
    secret = security.tao_bi_mat_totp()
    ma = security.totp(secret)
    assert len(ma) == 6 and ma.isdigit()
    assert security.kiem_totp(secret, ma)
    # Lệch 1 bước vẫn chấp nhận; lệch xa thì không.
    assert security.kiem_totp(secret, ma, at=__import__("time").time() + 30)
    sai = "000000" if ma != "000000" else "111111"
    assert not security.kiem_totp(secret, sai, cua_so=0)
    assert not security.kiem_totp(secret, "abc")


def test_ma_du_phong_hash_khong_luu_plaintext():
    ma = security.tao_ma_du_phong()
    h = security.bam_ma_du_phong(ma)
    assert len(h) == 64 and h != ma
    assert h == security.bam_ma_du_phong(ma.lower().replace("-", " "))


def test_bat_mfa_va_dang_nhap_hai_lop(client, owner):
    tao_user("employee", "mfa-user", dept="kinh-doanh")
    secret, codes = _bat_mfa("mfa-user")
    assert len(codes) == 10

    r = dang_nhap(client, "mfa-user", "User!Passw0rd")
    assert r.status_code == 303 and r.headers["location"].startswith("/dang-nhap/mfa")

    page = client.get("/dang-nhap/mfa?next=/")
    assert page.status_code == 200 and "Xác thực 2 lớp" in page.text
    token = csrf_tu(page.text)
    ok = client.post("/dang-nhap/mfa", data={
        "_csrf": token, "next": "/", "ma": security.totp(secret)}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/"
    assert client.get("/api/me").status_code == 200
    assert client.get("/ho-so/mfa").status_code == 200


def test_ma_du_phong_chi_dung_mot_lan(client, owner):
    tao_user("employee", "mfa-backup", dept="kinh-doanh")
    _, codes = _bat_mfa("mfa-backup")
    ma = codes[0]

    def _login_va_nhap(ma_nhap: str):
        dang_nhap(client, "mfa-backup", "User!Passw0rd")
        page = client.get("/dang-nhap/mfa")
        return client.post("/dang-nhap/mfa", data={
            "_csrf": csrf_tu(page.text), "next": "/", "ma": ma_nhap},
            follow_redirects=False)

    r1 = _login_va_nhap(ma)
    assert r1.status_code == 303 and r1.headers["location"] == "/"
    # Phiên mới: dùng lại đúng mã dự phòng phải bị từ chối.
    client.cookies.clear()
    r2 = _login_va_nhap(ma)
    assert r2.status_code == 303 and r2.headers["location"].startswith("/dang-nhap/mfa")
    assert client.get("/api/me").status_code == 401


def test_tat_mfa_can_mat_khau_va_ma(client, owner):
    tao_user("employee", "mfa-off", dept="kinh-doanh")
    secret, _ = _bat_mfa("mfa-off")
    conn = db.connect()
    try:
        user = auth.nguoi_dung_day_du(conn, "mfa-off")
        with pytest.raises(ValidationError):
            auth.tat_mfa(conn, user, "SaiMatKhau!", security.totp(secret))
        auth.tat_mfa(conn, user, "User!Passw0rd", security.totp(secret))
        user = auth.nguoi_dung_day_du(conn, "mfa-off")
        assert user["mfa_enabled"] == 0
        assert auth.ma_du_phong_con_lai(conn, "mfa-off") == 0
    finally:
        conn.close()
    # Sau khi tắt, đăng nhập chỉ cần mật khẩu.
    r = dang_nhap(client, "mfa-off", "User!Passw0rd")
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_login_thuong_khong_bi_anh_huong(client, owner):
    tao_user("employee", "no-mfa", dept="kinh-doanh")
    r = dang_nhap(client, "no-mfa", "User!Passw0rd")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert client.get("/api/me").status_code == 200


def test_cli_mfa_reset(client, owner):
    tao_user("employee", "mfa-cli", dept="kinh-doanh")
    _bat_mfa("mfa-cli")
    assert cli.main(["mfa-reset", "--id", "mfa-cli"]) == 0
    conn = db.connect()
    try:
        user = auth.nguoi_dung_day_du(conn, "mfa-cli")
        assert user["mfa_enabled"] == 0 and not user["mfa_secret"]
        assert auth.ma_du_phong_con_lai(conn, "mfa-cli") == 0
    finally:
        conn.close()


def test_bat_mfa_qua_giao_dien(client, owner):
    tao_user("employee", "mfa-ui", dept="kinh-doanh")
    assert dang_nhap(client, "mfa-ui", "User!Passw0rd").status_code == 303
    page = client.get("/ho-so/mfa")
    assert page.status_code == 200 and "Bật xác thực 2 lớp" in page.text
    import re
    secret = re.search(r'id="mfa-secret">([^<]+)</code>', page.text).group(1).strip()
    r = client.post("/ho-so/mfa/bat", data={
        "_csrf": csrf_tu(page.text), "secret": secret,
        "ma": security.totp(secret), "matKhau": "User!Passw0rd"},
        follow_redirects=False)
    assert r.status_code == 200 and "Lưu 10 mã này" in r.text
    conn = db.connect()
    try:
        user = auth.nguoi_dung_day_du(conn, "mfa-ui")
        assert user["mfa_enabled"] == 1 and user["mfa_secret"] == secret
        assert auth.ma_du_phong_con_lai(conn, "mfa-ui") == 10
    finally:
        conn.close()
    assert client.get("/ho-so/mfa").status_code == 200
