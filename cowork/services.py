"""Nghiệp vụ COWORK: tài khoản, ban, quyền module, vai trò, cài đặt, vé Brain."""
from __future__ import annotations

import json
import re
import sqlite3

from . import audit, auth, brain, config, db, rbac, security
from .errors import Conflict, Forbidden, NotFound, ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# ------------------------------------------------------------------ tiện ích
def _email_hop_le(email: str) -> bool:
    return not email or bool(EMAIL_RE.match(email))


def _kiem_tra_mat_khau(conn: sqlite3.Connection, mat_khau: str, user_id: str) -> None:
    try:
        minimum = int(db.get_setting(conn, "security.password_min", str(config.PASSWORD_MIN)))
    except (TypeError, ValueError):
        minimum = config.PASSWORD_MIN
    loi = security.kiem_tra_do_manh(mat_khau, user_id, minimum)
    if loi:
        raise ValidationError(loi)


def _lay_ban(conn: sqlite3.Connection, tenant_id: str, department_id: str | None) -> dict | None:
    if not department_id:
        return None
    row = conn.execute("SELECT * FROM departments WHERE id=? AND tenant_id=?",
                       (department_id, tenant_id)).fetchone()
    return dict(row) if row else None


def _bat_buoc_ban(role_code: str) -> bool:
    return role_code in (rbac.MANAGER, rbac.EMPLOYEE)


def _kiem_tra_pham_vi_ban(conn: sqlite3.Connection, actor: dict, dept_id: str | None) -> None:
    # Super Admin toàn quyền; mọi vai trò khác chỉ thao tác trong phạm vi của mình.
    # Vai trò không có phạm vi (nhân viên/đối tác) trả về tập rỗng ⇒ bị chặn.
    if actor["role_code"] == rbac.SUPER:
        return
    if not rbac.trong_pham_vi(conn, actor, dept_id):
        raise Forbidden("Ban/bộ phận này nằm ngoài phạm vi bạn được uỷ quyền.")


def _thong_bao_ban(conn: sqlite3.Connection, dept_id: str | None) -> str:
    if not dept_id:
        return "—"
    row = conn.execute("SELECT name FROM departments WHERE id=?", (dept_id,)).fetchone()
    return row["name"] if row else dept_id


# ------------------------------------------------------------------ tài khoản
def tao_nguoi_dung(conn: sqlite3.Connection, actor: dict, perms: set[str], data: dict,
                   request=None) -> tuple[dict, str | None]:
    rbac.doi_quyen(actor, perms, "accounts.create", "Bạn không có quyền tạo tài khoản.")
    user_id = security.chuan_hoa_id(data.get("id", ""))
    if (loi := security.kiem_tra_id(user_id)):
        raise ValidationError(loi)
    if conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
        raise Conflict(f"ID '{user_id}' đã tồn tại. ID là duy nhất toàn hệ thống.")
    display_name = (data.get("display_name") or "").strip()[:120]
    if len(display_name) < 2:
        raise ValidationError("Tên hiển thị phải có ít nhất 2 ký tự.")
    email = (data.get("email") or "").strip()[:190]
    if not _email_hop_le(email):
        raise ValidationError("Email không hợp lệ.")
    phone = (data.get("phone") or "").strip()[:40]
    role_code = (data.get("role_code") or "").strip()
    role = rbac.lay_vai_tro(conn, role_code)
    if not role:
        raise ValidationError("Vai trò không hợp lệ.")
    rbac.kiem_tra_gan_vai_tro(conn, actor, role_code)
    if role_code == rbac.ADMIN and not rbac.la_super(actor):
        raise Forbidden("Chỉ Super Admin được tạo tài khoản Quản trị cấp dưới.")
    dept_id = (data.get("department_id") or "").strip() or None
    if _bat_buoc_ban(role_code) and not dept_id:
        raise ValidationError("Trưởng ban và nhân viên phải thuộc một ban/bộ phận.")
    if dept_id and not _lay_ban(conn, actor["tenant_id"], dept_id):
        raise ValidationError("Ban/bộ phận không tồn tại trong tenant.")
    _kiem_tra_pham_vi_ban(conn, actor, dept_id)
    partner_org = (data.get("partner_org") or "").strip()[:160]
    if role_code == rbac.PARTNER and not partner_org:
        raise ValidationError("Đối tác phải có tên tổ chức/hợp đồng.")
    mat_khau = data.get("password") or ""
    temp = None
    if not mat_khau:
        temp = security.gen_mat_khau()
        mat_khau = temp
        must_change = 1
    else:
        _kiem_tra_mat_khau(conn, mat_khau, user_id)
        must_change = 1 if str(data.get("must_change", "0")) in ("1", "on", "true") else 0
    hash_b64, salt_b64 = security.bam_mat_khau(mat_khau)
    now = db.now_iso()
    conn.execute(
        "INSERT INTO users(id, tenant_id, display_name, email, phone, role_code, department_id, "
        "partner_org, status, password_hash, password_salt, password_algo, must_change_password, "
        "created_by, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?, 'active', ?,?, 'scrypt', ?,?,?,?)",
        (user_id, actor["tenant_id"], display_name, email or None, phone or None, role_code,
         dept_id, partner_org or None, hash_b64, salt_b64, must_change, actor["id"], now, now),
    )
    conn.commit()
    if role_code == rbac.ADMIN:
        _luu_scope_admin(conn, actor, user_id, data, request)
    user = auth.nguoi_dung_day_du(conn, user_id)
    audit.ghi(conn, actor, "account.create", target_type="user", target_id=user_id,
              detail={"vaiTro": role_code, "ban": dept_id, "coMatKhauTam": bool(temp)},
              request=request)
    return user, temp


def _luu_scope_admin(conn: sqlite3.Connection, actor: dict, user_id: str, data: dict,
                     request=None) -> None:
    """Chỉ Super Admin được đặt phạm vi cho quản trị cấp dưới."""
    if actor["role_code"] != rbac.SUPER:
        # Không bao giờ mặc định phạm vi toàn tenant cho người không phải Super Admin.
        raise Forbidden("Chỉ Super Admin được đặt phạm vi quản trị.")
    mode = (data.get("scope_mode") or "tenant").strip()
    conn.execute("DELETE FROM admin_scopes WHERE user_id=?", (user_id,))
    if mode == "tenant":
        conn.execute("INSERT INTO admin_scopes(tenant_id, user_id, department_id, created_at, "
                     "created_by) VALUES(?,?,NULL,?,?)",
                     (actor["tenant_id"], user_id, db.now_iso(), actor["id"]))
    else:
        for dept_id in data.get("scope_departments") or []:
            if _lay_ban(conn, actor["tenant_id"], dept_id):
                conn.execute("INSERT OR IGNORE INTO admin_scopes(tenant_id, user_id, department_id, "
                             "created_at, created_by) VALUES(?,?,?,?,?)",
                             (actor["tenant_id"], user_id, dept_id, db.now_iso(), actor["id"]))
    conn.commit()
    audit.ghi(conn, actor, "account.scope", target_type="user", target_id=user_id,
              detail={"mode": mode, "soBan": len(data.get("scope_departments") or [])},
              request=request)


def cap_nhat_nguoi_dung(conn: sqlite3.Connection, actor: dict, perms: set[str], target: dict,
                        data: dict, request=None) -> dict:
    rbac.kiem_tra_quan_ly(conn, actor, perms, target, "accounts.update")
    old = dict(target)
    display_name = (data.get("display_name") or target["display_name"]).strip()[:120]
    if len(display_name) < 2:
        raise ValidationError("Tên hiển thị phải có ít nhất 2 ký tự.")
    email = (data.get("email") or "").strip()[:190]
    if email and not _email_hop_le(email):
        raise ValidationError("Email không hợp lệ.")
    phone = (data.get("phone") or "").strip()[:40]
    role_code = (data.get("role_code") or target["role_code"]).strip()
    role = rbac.lay_vai_tro(conn, role_code)
    if not role:
        raise ValidationError("Vai trò không hợp lệ.")
    if role_code != target["role_code"]:
        rbac.kiem_tra_gan_vai_tro(conn, actor, role_code)
        rbac.kiem_tra_khong_tu_nang(actor, target["id"])
    dept_id = (data.get("department_id") or "").strip() or None
    if _bat_buoc_ban(role_code) and not dept_id:
        raise ValidationError("Trưởng ban và nhân viên phải thuộc một ban/bộ phận.")
    if dept_id and not _lay_ban(conn, actor["tenant_id"], dept_id):
        raise ValidationError("Ban/bộ phận không tồn tại trong tenant.")
    _kiem_tra_pham_vi_ban(conn, actor, dept_id)
    partner_org = (data.get("partner_org") or "").strip()[:160]
    if role_code == rbac.PARTNER and not partner_org:
        raise ValidationError("Đối tác phải có tên tổ chức/hợp đồng.")
    conn.execute(
        "UPDATE users SET display_name=?, email=?, phone=?, role_code=?, department_id=?, "
        "partner_org=?, updated_at=? WHERE id=?",
        (display_name, email or None, phone or None, role_code, dept_id,
         partner_org or None, db.now_iso(), target["id"]),
    )
    if role_code != rbac.ADMIN:
        conn.execute("DELETE FROM admin_scopes WHERE user_id=?", (target["id"],))
    conn.commit()
    if role_code != old["role_code"] or dept_id != old["department_id"]:
        auth.thu_hoi_cua_user(conn, target["id"], actor["id"], "Vai trò/ban thay đổi")
        brain.thu_hoi_phien(conn, target["id"], "COWORK đổi vai trò/ban")
    audit.ghi(conn, actor, "account.update", target_type="user", target_id=target["id"],
              detail={"truoc": {"vaiTro": old["role_code"], "ban": old["department_id"]},
                      "sau": {"vaiTro": role_code, "ban": dept_id}}, request=request)
    return auth.nguoi_dung_day_du(conn, target["id"])


def cap_nhat_ho_so(conn: sqlite3.Connection, user: dict, data: dict, request=None) -> None:
    display_name = (data.get("display_name") or user["display_name"]).strip()[:120]
    if len(display_name) < 2:
        raise ValidationError("Tên hiển thị phải có ít nhất 2 ký tự.")
    email = (data.get("email") or "").strip()[:190]
    if email and not _email_hop_le(email):
        raise ValidationError("Email không hợp lệ.")
    phone = (data.get("phone") or "").strip()[:40]
    conn.execute("UPDATE users SET display_name=?, email=?, phone=?, updated_at=? WHERE id=?",
                 (display_name, email or None, phone or None, db.now_iso(), user["id"]))
    conn.commit()
    audit.ghi(conn, user, "profile.update", target_type="user", target_id=user["id"],
              detail={"email": email}, request=request)


def doi_mat_khau(conn: sqlite3.Connection, user: dict, mat_khau_cu: str, mat_khau_moi: str,
                 request=None) -> None:
    row = conn.execute("SELECT password_hash, password_salt FROM users WHERE id=?",
                       (user["id"],)).fetchone()
    if not row or not security.kiem_mat_khau(mat_khau_cu, row["password_hash"], row["password_salt"]):
        raise ValidationError("Mật khẩu hiện tại không đúng.")
    _kiem_tra_mat_khau(conn, mat_khau_moi, user["id"])
    if mat_khau_cu == mat_khau_moi:
        raise ValidationError("Mật khẩu mới phải khác mật khẩu hiện tại.")
    hash_b64, salt_b64 = security.bam_mat_khau(mat_khau_moi)
    conn.execute("UPDATE users SET password_hash=?, password_salt=?, must_change_password=0, "
                 "token_version=token_version+1, updated_at=? WHERE id=?",
                 (hash_b64, salt_b64, db.now_iso(), user["id"]))
    conn.commit()
    auth.thu_hoi_cua_user(conn, user["id"], user["id"], "Đổi mật khẩu")
    audit.ghi(conn, user, "profile.password", target_type="user", target_id=user["id"],
              detail="Đổi mật khẩu; thu hồi mọi phiên khác", request=request)


def dat_lai_mat_khau(conn: sqlite3.Connection, actor: dict, perms: set[str], target: dict,
                     request=None) -> str:
    rbac.kiem_tra_quan_ly(conn, actor, perms, target, "accounts.reset_password")
    temp = security.gen_mat_khau()
    hash_b64, salt_b64 = security.bam_mat_khau(temp)
    conn.execute("UPDATE users SET password_hash=?, password_salt=?, must_change_password=1, "
                 "token_version=token_version+1, updated_at=? WHERE id=?",
                 (hash_b64, salt_b64, db.now_iso(), target["id"]))
    conn.commit()
    auth.thu_hoi_cua_user(conn, target["id"], actor["id"], "Đặt lại mật khẩu")
    brain.thu_hoi_phien(conn, target["id"], "COWORK đặt lại mật khẩu")
    audit.ghi(conn, actor, "account.reset_password", target_type="user", target_id=target["id"],
              detail={"batBuocDoi": True}, request=request)
    return temp


def doi_trang_thai(conn: sqlite3.Connection, actor: dict, perms: set[str], target: dict,
                   trang_thai: str, request=None) -> None:
    rbac.kiem_tra_quan_ly(conn, actor, perms, target, "accounts.suspend")
    if trang_thai not in ("active", "suspended"):
        raise ValidationError("Trạng thái không hợp lệ.")
    if trang_thai == "suspended" and target["role_code"] == rbac.SUPER:
        raise Forbidden("Không thể khoá Super Admin.")
    conn.execute("UPDATE users SET status=?, updated_at=? WHERE id=?",
                 (trang_thai, db.now_iso(), target["id"]))
    if trang_thai == "active":
        # Mở khoá phải xoá bộ đếm đăng nhập sai của CHÍNH tài khoản này (mọi IP),
        # nếu không người dùng vẫn bị rate-limit chặn dù tài khoản đã hoạt động lại.
        conn.execute("DELETE FROM login_attempts WHERE user_id=? AND success=0",
                     (target["id"],))
    conn.commit()
    if trang_thai == "suspended":
        auth.thu_hoi_cua_user(conn, target["id"], actor["id"], "Tài khoản bị khoá")
        brain.thu_hoi_phien(conn, target["id"], "COWORK khoá tài khoản")
    audit.ghi(conn, actor, "account.suspend" if trang_thai == "suspended" else "account.activate",
              target_type="user", target_id=target["id"], request=request)


def luu_tru_nguoi_dung(conn: sqlite3.Connection, actor: dict, perms: set[str], target: dict,
                       request=None) -> None:
    rbac.kiem_tra_quan_ly(conn, actor, perms, target, "accounts.archive")
    if target["role_code"] == rbac.SUPER:
        raise Forbidden("Không thể lưu trữ Super Admin.")
    conn.execute("UPDATE users SET status='archived', mfa_enabled=0, mfa_secret=NULL, "
                 "updated_at=? WHERE id=?", (db.now_iso(), target["id"]))
    # Scope/MFA của tài khoản đã lưu trữ không còn giá trị.
    conn.execute("DELETE FROM admin_scopes WHERE user_id=?", (target["id"],))
    conn.execute("DELETE FROM mfa_backup_codes WHERE user_id=?", (target["id"],))
    conn.execute("DELETE FROM mfa_challenges WHERE user_id=?", (target["id"],))
    conn.commit()
    auth.thu_hoi_cua_user(conn, target["id"], actor["id"], "Tài khoản bị lưu trữ")
    brain.thu_hoi_phien(conn, target["id"], "COWORK lưu trữ tài khoản")
    audit.ghi(conn, actor, "account.archive", target_type="user", target_id=target["id"],
              request=request)


# ------------------------------------------------------------------ phân quyền module
def _quyen_module(module_code: str) -> tuple[str, str]:
    return f"{module_code}.view", f"{module_code}.use"


def trang_thai_quyen_module(conn: sqlite3.Connection, target: dict) -> list[dict]:
    role_perms = {r["permission_code"] for r in conn.execute(
        "SELECT permission_code FROM role_permissions WHERE role_code=?",
        (target["role_code"],)).fetchall()}
    overrides = {r["permission_code"]: r["effect"] for r in conn.execute(
        "SELECT permission_code, effect FROM user_permissions WHERE user_id=?",
        (target["id"],)).fetchall()}
    ma_quyen_ton_tai = {r["code"] for r in conn.execute("SELECT code FROM permissions").fetchall()}
    rows = []
    for m in conn.execute("SELECT * FROM modules ORDER BY sort_order").fetchall():
        m = dict(m)
        view, use = _quyen_module(m["code"])
        default = "use" if use in role_perms else ("view" if view in role_perms else "none")
        eff_view = overrides.get(view, "allow" if view in role_perms else "deny") == "allow"
        eff_use = overrides.get(use, "allow" if use in role_perms else "deny") == "allow"
        if not eff_view:
            mode = "block"
        elif eff_use:
            mode = "use"
        else:
            mode = "view"
        co_override = view in overrides or use in overrides
        rows.append({
            "code": m["code"], "name": m["name"], "status": m["status"],
            "default": default, "mode": mode if co_override else "default",
            "effective": "block" if not eff_view else ("use" if eff_use else "view"),
            "view": view, "use": use,
            # Module không có quyền `<code>.use` (dashboard, accounts, roles…) thì UI
            # phải khoá lựa chọn "Sử dụng"; service quy đổi an toàn thành "chỉ xem".
            "has_use": use in ma_quyen_ton_tai,
        })
    return rows


def dat_quyen_module(conn: sqlite3.Connection, actor: dict, perms: set[str], target: dict,
                     lua_chon: dict[str, str], request=None) -> dict:
    rbac.doi_quyen(actor, perms, "permissions.grant", "Bạn không có quyền cấp/thu hồi module.")
    if actor["id"] == target["id"]:
        raise Forbidden("Không thể tự thay đổi quyền module của chính mình.")
    if target["role_code"] == rbac.SUPER:
        raise Forbidden("Không thể thay đổi quyền của Super Admin.")
    if not rbac.co_the_quan_ly(conn, actor, perms, target, "permissions.grant"):
        raise Forbidden("Tài khoản ngoài phạm vi hoặc không đủ cấp để phân quyền.")
    hop_le = {r["code"]: dict(r) for r in conn.execute("SELECT * FROM modules").fetchall()}
    hop_le_quyen = {r["code"] for r in conn.execute("SELECT code FROM permissions").fetchall()}

    def _ma_quyen(module_code: str) -> tuple[list[str], list[str]]:
        """Chỉ trả mã quyền THỰC SỰ tồn tại cho module.

        Nhiều module (accounts, departments, roles…) chỉ có view + action, không
        có `<module>.use`. Ghi thẳng `use` sẽ vi phạm khoá ngoại (lỗi 500).
        Với các module đó, mức "sử dụng" tương đương "chỉ xem" ở tầng module.
        """
        view, use = _quyen_module(module_code)
        return ([view] if view in hop_le_quyen else [],
                [use] if use in hop_le_quyen else [])

    # Kiểm tra TOÀN BỘ lựa chọn trước khi ghi: tránh thu hồi dở dang nếu một
    # module sau đó bị từ chối (DB chạy autocommit).
    for module_code, mode in lua_chon.items():
        if module_code not in hop_le:
            continue
        if mode not in ("default", "view", "use", "block"):
            raise ValidationError(f"Lựa chọn quyền không hợp lệ cho module {module_code}.")
        if mode in ("view", "use"):
            view_codes, use_codes = _ma_quyen(module_code)
            for code in (view_codes if mode == "view" else view_codes + use_codes):
                rbac.kiem_tra_cap_quyen(actor, perms, code)
    before = {r["code"]: r["mode"] for r in trang_thai_quyen_module(conn, target)}
    for module_code, mode in lua_chon.items():
        if module_code not in hop_le:
            continue
        view_codes, use_codes = _ma_quyen(module_code)
        codes = view_codes + use_codes
        if codes:
            conn.execute(
                "DELETE FROM user_permissions WHERE user_id=? AND permission_code IN ("
                + ",".join("?" * len(codes)) + ")", (target["id"], *codes))
        if mode == "default":
            continue
        allow = []
        deny = []
        if mode == "block":
            deny = codes
        elif mode == "view":
            allow = view_codes
            deny = use_codes
        elif mode == "use":
            allow = view_codes + use_codes
        for code, effect in [(c, "allow") for c in allow] + [(c, "deny") for c in deny]:
            conn.execute(
                "INSERT INTO user_permissions(tenant_id, user_id, permission_code, effect, "
                "granted_by, granted_at) VALUES(?,?,?,?,?,?)",
                (target["tenant_id"], target["id"], code, effect, actor["id"], db.now_iso()))
    conn.commit()
    after = {r["code"]: r["mode"] for r in trang_thai_quyen_module(conn, target)}
    thay_doi = {k: {"truoc": before.get(k), "sau": after.get(k)}
                for k in after if before.get(k) != after.get(k)}
    audit.ghi(conn, actor, "permissions.update", target_type="user", target_id=target["id"],
              detail={"thayDoi": thay_doi}, request=request)
    # Nếu mất quyền Brain thì thu hồi phiên Brain ngay.
    user_moi = auth.nguoi_dung_day_du(conn, target["id"])
    perms_moi = rbac.quyen_hieu_luc(conn, user_moi) if user_moi else set()
    if "brain.use" not in perms_moi or "brain.view" not in perms_moi:
        brain.thu_hoi_phien(conn, target["id"], "COWORK thu hồi quyền module Brain")
    return thay_doi


# ------------------------------------------------------------------ ban / bộ phận
def tao_ban(conn: sqlite3.Connection, actor: dict, perms: set[str], data: dict,
            request=None) -> dict:
    rbac.doi_quyen(actor, perms, "departments.create", "Bạn không có quyền tạo ban/bộ phận.")
    scope = rbac.pham_vi_ban(conn, actor)
    if scope is not None:
        raise Forbidden("Chỉ quản trị toàn tenant mới được tạo ban mới.")
    name = (data.get("name") or "").strip()[:120]
    if len(name) < 2:
        raise ValidationError("Tên ban phải có ít nhất 2 ký tự.")
    code = (data.get("code") or security.slug(name, 30)).strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,39}$", code):
        raise ValidationError("Mã ban chỉ gồm a-z, 0-9 và dấu gạch ngang.")
    # `departments.id` hiện là duy nhất TOÀN HỆ THỐNG (id = code). Kiểm tra toàn
    # cục để tránh IntegrityError 500 khi tenant khác đã dùng cùng mã.
    if conn.execute("SELECT 1 FROM departments WHERE id=? OR (tenant_id=? AND code=?)",
                    (code, actor["tenant_id"], code)).fetchone():
        raise Conflict("Mã ban đã tồn tại (mã ban là duy nhất toàn hệ thống).")
    now = db.now_iso()
    dept_id = code
    conn.execute(
        "INSERT INTO departments(id, tenant_id, code, name, parent_id, manager_user_id, "
        "description, status, created_at, updated_at) VALUES(?,?,?,?,NULL,NULL,?, 'active', ?, ?)",
        (dept_id, actor["tenant_id"], code, name, (data.get("description") or "").strip()[:500],
         now, now))
    conn.commit()
    audit.ghi(conn, actor, "department.create", target_type="department", target_id=dept_id,
              detail={"ten": name, "ma": code}, request=request)
    return {"id": dept_id, "code": code, "name": name}


def cap_nhat_ban(conn: sqlite3.Connection, actor: dict, perms: set[str], dept: dict,
                 data: dict, request=None) -> None:
    rbac.doi_quyen(actor, perms, "departments.update", "Bạn không có quyền sửa ban/bộ phận.")
    if dept.get("tenant_id") != actor["tenant_id"]:
        raise Forbidden("Ban/bộ phận này không thuộc tenant của bạn.")
    if not rbac.trong_pham_vi(conn, actor, dept["id"]):
        raise Forbidden("Ban này nằm ngoài phạm vi bạn được uỷ quyền.")
    name = (data.get("name") or dept["name"]).strip()[:120]
    if len(name) < 2:
        raise ValidationError("Tên ban phải có ít nhất 2 ký tự.")
    desc = (data.get("description") or "").strip()[:500]
    manager_id = (data.get("manager_user_id") or "").strip() or None
    if manager_id:
        mgr = conn.execute("SELECT * FROM users WHERE id=? AND tenant_id=?",
                           (manager_id, actor["tenant_id"])).fetchone()
        if not mgr:
            raise ValidationError("Trưởng ban không tồn tại trong tenant.")
        if mgr["status"] != "active":
            raise ValidationError("Trưởng ban phải là tài khoản đang hoạt động.")
        if rbac.cap_vai_tro(conn, mgr["role_code"]) < rbac.cap_vai_tro(conn, rbac.MANAGER):
            raise ValidationError("Trưởng ban phải có vai trò Trưởng ban hoặc cao hơn.")
        # Gán trưởng ban là thao tác lên tài khoản đó: phải trong phạm vi, thấp hơn
        # cấp và không được là Super Admin/tài khoản đã lưu trữ.
        if not rbac.co_the_quan_ly(conn, actor, perms, dict(mgr), "departments.update"):
            raise Forbidden("Bạn không được gán người này làm trưởng ban "
                            "(khác cấp, ngoài phạm vi hoặc tài khoản đã lưu trữ).")
        conn.execute("UPDATE users SET department_id=?, updated_at=? WHERE id=?",
                     (dept["id"], db.now_iso(), manager_id))
    conn.execute("UPDATE departments SET name=?, description=?, manager_user_id=?, updated_at=? "
                 "WHERE id=?", (name, desc or None, manager_id, db.now_iso(), dept["id"]))
    conn.commit()
    audit.ghi(conn, actor, "department.update", target_type="department", target_id=dept["id"],
              detail={"ten": name, "truongBan": manager_id}, request=request)


def luu_tru_ban(conn: sqlite3.Connection, actor: dict, perms: set[str], dept: dict,
                request=None) -> None:
    rbac.doi_quyen(actor, perms, "departments.delete", "Bạn không có quyền lưu trữ ban.")
    if dept.get("tenant_id") != actor["tenant_id"]:
        raise Forbidden("Ban/bộ phận này không thuộc tenant của bạn.")
    if not rbac.trong_pham_vi(conn, actor, dept["id"]):
        raise Forbidden("Ban này nằm ngoài phạm vi bạn được uỷ quyền.")
    so_nguoi = conn.execute(
        "SELECT COUNT(*) FROM users WHERE department_id=? AND status<>'archived'",
        (dept["id"],)).fetchone()[0]
    if so_nguoi:
        raise Conflict(f"Ban còn {so_nguoi} nhân sự đang hoạt động — chuyển họ sang ban khác trước.")
    conn.execute("UPDATE departments SET status='archived', updated_at=? WHERE id=?",
                 (db.now_iso(), dept["id"]))
    conn.commit()
    audit.ghi(conn, actor, "department.archive", target_type="department", target_id=dept["id"],
              request=request)


# ------------------------------------------------------------------ vai trò
def _kiem_tra_tenant_cau_hinh(actor: dict) -> None:
    """Vai trò/module/cài đặt là cấu hình TOÀN HỆ THỐNG (schema hiện chưa tenant-scoped).

    Chỉ Super Admin của tenant gốc mới được sửa, để tenant khác không thay đổi
    ma trận quyền/module/setting ảnh hưởng tenant gốc. Người dùng tenant khác vẫn
    được quản lý tài khoản/ban trong tenant của mình theo phân quyền thường.
    """
    if actor["tenant_id"] != config.TENANT_MAC_DINH:
        raise Forbidden("Cấu hình vai trò/module/cài đặt là toàn hệ thống; "
                        "chỉ Super Admin tenant gốc được sửa.")


def cap_nhat_quyen_vai_tro(conn: sqlite3.Connection, actor: dict, perms: set[str],
                           role_code: str, quyen: list[str], request=None) -> dict:
    rbac.doi_quyen(actor, perms, "roles.manage", "Chỉ Super Admin được sửa quyền vai trò.")
    _kiem_tra_tenant_cau_hinh(actor)
    role = rbac.lay_vai_tro(conn, role_code)
    if not role:
        raise NotFound("Vai trò không tồn tại.")
    if role_code == rbac.SUPER or role["is_locked"]:
        raise Forbidden("Vai trò Super Admin được khoá, không thể sửa.")
    if not rbac.co_the_sua_vai_tro(conn, actor, perms, role_code):
        raise Forbidden("Bạn chỉ được sửa vai trò thấp hơn cấp của mình và cần cả "
                        "quyền 'roles.manage' lẫn 'permissions.grant'.")
    hop_le = {r["code"] for r in conn.execute("SELECT code FROM permissions").fetchall()}
    moi = {p for p in quyen if p in hop_le}
    # Quyền hành động phải đi kèm quyền xem module.
    for p in list(moi):
        if "." in p:
            module_code = p.split(".", 1)[0]
            if p.split(".", 1)[1] != "view":
                moi.add(f"{module_code}.view")
    moi &= hop_le
    # Quyền miễn nhiễm chỉ thuộc về vai trò Super Admin.
    if moi & rbac.QUYEN_CHI_SUPER:
        raise Forbidden("Không thể gán quyền chỉ dành cho Super Admin cho vai trò khác.")
    cu = {r["permission_code"] for r in conn.execute(
        "SELECT permission_code FROM role_permissions WHERE role_code=?", (role_code,)).fetchall()}
    if not rbac.la_super(actor):
        # Chỉ được thêm quyền mình có (subset) và chỉ được thu hồi quyền mình có.
        for p in sorted(moi - cu):
            rbac.kiem_tra_cap_quyen(actor, perms, p)
        for p in sorted(cu - moi):
            if p not in perms:
                raise Forbidden(f"Không thể thu hồi quyền '{p}' vì bạn không có quyền này.")
    # Mọi kiểm tra xong mới ghi, tránh làm mất ma trận quyền khi bị từ chối.
    conn.execute("DELETE FROM role_permissions WHERE role_code=?", (role_code,))
    conn.executemany("INSERT INTO role_permissions(role_code, permission_code) VALUES(?,?)",
                     [(role_code, p) for p in sorted(moi)])
    conn.commit()
    audit.ghi(conn, actor, "role.permissions", target_type="role", target_id=role_code,
              detail={"them": sorted(moi - cu), "bot": sorted(cu - moi)}, request=request)
    return {"them": sorted(moi - cu), "bot": sorted(cu - moi)}


# ------------------------------------------------------------------ module registry
def cap_nhat_module(conn: sqlite3.Connection, actor: dict, perms: set[str], module: dict,
                    data: dict, request=None) -> None:
    rbac.doi_quyen(actor, perms, "modules.manage", "Chỉ Super Admin được quản lý module.")
    if not rbac.la_super(actor):
        raise Forbidden("Chỉ Super Admin được quản lý module.")
    _kiem_tra_tenant_cau_hinh(actor)
    if module["code"] in ("dashboard", "accounts", "settings"):
        raise Forbidden("Module nền tảng không thể tắt.")
    status = "active" if str(data.get("status", module["status"])) == "active" else "disabled"
    name = (data.get("name") or module["name"]).strip()[:120]
    desc = (data.get("description") or "").strip()[:500]
    conn.execute("UPDATE modules SET name=?, description=?, status=? WHERE code=?",
                 (name, desc or None, status, module["code"]))
    conn.commit()
    audit.ghi(conn, actor, "module.update", target_type="module", target_id=module["code"],
              detail={"ten": name, "trangThai": status}, request=request)


# ------------------------------------------------------------------ cài đặt
CAI_DAT_CHO_PHEP = {
    "tenant.display_name", "security.session_hours", "security.idle_minutes",
    "security.password_min", "brain.enabled", "brain.base_url", "brain.public_url",
    "brain.allow_mfa_users", "branding.support_note",
}


def cap_nhat_cai_dat(conn: sqlite3.Connection, actor: dict, perms: set[str], data: dict,
                     request=None) -> list[str]:
    rbac.doi_quyen(actor, perms, "settings.manage", "Chỉ Super Admin được sửa cài đặt.")
    if not rbac.la_super(actor):
        # settings.manage/settings.view là quyền miễn nhiễm, không uỷ quyền được.
        raise Forbidden("Chỉ Super Admin được sửa cài đặt.")
    _kiem_tra_tenant_cau_hinh(actor)
    thay_doi = []
    for key in CAI_DAT_CHO_PHEP:
        if key not in data:
            continue
        value = str(data.get(key, "")).strip()
        if key == "security.session_hours":
            n = int(value or 12)
            if not 1 <= n <= 72:
                raise ValidationError("Số giờ phiên phải từ 1 đến 72.")
            value = str(n)
        elif key == "security.idle_minutes":
            n = int(value or 60)
            if not 5 <= n <= 720:
                raise ValidationError("Thời gian chờ phải từ 5 đến 720 phút.")
            value = str(n)
        elif key == "security.password_min":
            n = int(value or 10)
            if not 8 <= n <= 32:
                raise ValidationError("Độ dài mật khẩu tối thiểu phải từ 8 đến 32.")
            value = str(n)
        elif key in ("brain.enabled", "brain.allow_mfa_users"):
            value = "1" if value in ("1", "on", "true") else "0"
        elif key in ("brain.base_url", "brain.public_url"):
            if value and not re.match(r"^https?://[^\s]+$", value):
                raise ValidationError("URL Brain phải bắt đầu bằng http:// hoặc https://")
            value = value.rstrip("/")
        cu = db.get_setting(conn, key, "")
        if cu != value:
            db.set_setting(conn, key, value, actor["id"])
            thay_doi.append(key)
    if thay_doi:
        audit.ghi(conn, actor, "settings.update", target_type="settings", target_id=",".join(thay_doi),
                  detail={"khoa": thay_doi}, request=request)
    return thay_doi


# ------------------------------------------------------------------ bootstrap owner
def tao_super_admin(conn: sqlite3.Connection, user_id: str, mat_khau: str,
                    display_name: str = "", reset: bool = False,
                    tenant_id: str | None = None) -> dict:
    user_id = security.chuan_hoa_id(user_id)
    tenant = (tenant_id or config.TENANT_MAC_DINH).strip()
    if (loi := security.kiem_tra_id(user_id)):
        raise ValidationError(loi)
    _kiem_tra_mat_khau(conn, mat_khau, user_id)
    now = db.now_iso()
    conn.execute("INSERT OR IGNORE INTO tenants(id, name, status, created_at) VALUES(?,?, 'active', ?)",
                 (tenant, tenant, now))
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if row and row["role_code"] != rbac.SUPER:
        raise Conflict(f"ID '{user_id}' đã tồn tại với vai trò {row['role_code']}, không phải Super Admin.")
    if row and not reset:
        raise Conflict(f"Super Admin '{user_id}' đã tồn tại. Dùng --reset để đặt lại mật khẩu.")
    hash_b64, salt_b64 = security.bam_mat_khau(mat_khau)
    if row:
        conn.execute("UPDATE users SET display_name=?, password_hash=?, password_salt=?, "
                     "status='active', must_change_password=0, token_version=token_version+1, "
                     "updated_at=? WHERE id=?",
                     (display_name or row["display_name"], hash_b64, salt_b64, now, user_id))
    else:
        conn.execute(
            "INSERT INTO users(id, tenant_id, display_name, email, phone, role_code, "
            "department_id, partner_org, status, password_hash, password_salt, password_algo, "
            "must_change_password, created_by, created_at, updated_at) "
            "VALUES(?,?,?,NULL,NULL,?,NULL,NULL,'active',?,?,'scrypt',0,'bootstrap',?,?)",
            (user_id, tenant, display_name or user_id, rbac.SUPER,
             hash_b64, salt_b64, now, now))
    conn.commit()
    auth.thu_hoi_cua_user(conn, user_id, "bootstrap", "Bootstrap/đặt lại mật khẩu")
    audit.ghi(conn, "bootstrap", "owner.bootstrap", target_type="user", target_id=user_id,
              detail={"reset": bool(row)}, tenant_id=tenant)
    return {"id": user_id, "moi": not bool(row), "reset": bool(row)}


# ------------------------------------------------------------------ thống kê
def thong_ke(conn: sqlite3.Connection, user: dict, perms: set[str]) -> dict:
    tenant = user["tenant_id"]
    if rbac.la_super(user) or "accounts.view" in perms:
        scope = rbac.pham_vi_ban(conn, user)
        if scope is None:
            where, params = "tenant_id=?", [tenant]
        elif scope:
            cho = ",".join("?" * len(scope))
            where, params = f"tenant_id=? AND department_id IN ({cho})", [tenant, *scope]
        else:
            where, params = "tenant_id=? AND 0=1", [tenant]
        tong = conn.execute(f"SELECT COUNT(*) FROM users WHERE {where} AND status<>'archived'",
                            params).fetchone()[0]
        hoat_dong = conn.execute(f"SELECT COUNT(*) FROM users WHERE {where} AND status='active'",
                                 params).fetchone()[0]
        khoa = conn.execute(f"SELECT COUNT(*) FROM users WHERE {where} AND status='suspended'",
                            params).fetchone()[0]
    else:
        tong = hoat_dong = 1
        khoa = 0 if user["status"] == "active" else 1
    ds_ban = conn.execute("SELECT COUNT(*) FROM departments WHERE tenant_id=? AND status='active'",
                          (tenant,)).fetchone()[0]
    if not (rbac.la_super(user) or "accounts.view" in perms):
        # Người dùng thường chỉ biết ban của mình, không thấy tổng số ban toàn tenant.
        ds_ban = 1 if user.get("department_id") else 0
    phien = conn.execute("SELECT COUNT(*) FROM sessions WHERE tenant_id=? AND status='active'",
                         (tenant,)).fetchone()[0]
    if not (rbac.la_super(user) or "accounts.view" in perms):
        phien = conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id=? AND status='active'",
                             (user["id"],)).fetchone()[0]
    if rbac.la_super(user) or "accounts.view" in perms or "audit.view" in perms:
        audit_hom_nay = audit.dem_hom_nay(conn, tenant)
    else:
        # Người dùng thường chỉ thấy số sự kiện do CHÍNH MÌNH tạo, không phải
        # toàn tenant (tránh rò rỉ mức hoạt động của tổ chức).
        audit_hom_nay = int(conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE tenant_id=? AND actor_id=? AND created_at>=?",
            (tenant, user["id"], db.today_iso())).fetchone()[0])
    return {"tongNguoiDung": int(tong), "dangHoatDong": int(hoat_dong), "dangKhoa": int(khoa),
            "soBan": int(ds_ban), "phienSong": int(phien), "auditHomNay": audit_hom_nay}
