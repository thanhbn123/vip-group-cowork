"""AG-01 FRONTEND — kiểm thử giao diện COWORK.

Phạm vi:
  * Đăng nhập 3 vai trò thật (Super Admin / Quản trị / Nhân viên) trên DB tạm.
  * Menu hiển thị khớp đúng module trong /api/me; nhân viên chỉ có 5 module.
  * Crawl toàn bộ href nội bộ trong HTML đã render, không có link 404/500.
  * Mọi form POST có input name="_csrf" (CSP/CSRF của COWORK).
  * Không có script/style/onclick inline trong template (CSP chặt).
  * Trang lỗi 403/404 render đúng template, không lộ link ngoài quyền.

Chỉ đọc mã ứng dụng; không sửa route/service/schema/auth.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi.testclient import TestClient

from cowork import auth, db, rbac, services
from cowork.main import app

ROOT = Path(__file__).resolve().parents[1]
OWNER_ID = "anh-thanh"
OWNER_PW = (ROOT / "secrets" / "owner-anh-thanh.txt").read_text(encoding="utf-8").strip()
ADMIN_ID, ADMIN_PW = "quan-tri-01", "Qt01!Passw0rd"
EMPLOYEE_ID, EMPLOYEE_PW = "nhan-vien-01", "Nv01!Passw0rd"

# Toàn bộ màn hình AG-01 phải kiểm tra (đăng nhập bằng Super Admin).
OWNER_SCREENS = [
    "/",
    "/tai-khoan",
    "/tai-khoan/tao-moi",
    "/tai-khoan/nhan-vien-01",
    "/tai-khoan/nhan-vien-01/phan-quyen",
    "/phan-quyen",
    "/ban",
    "/ban/tao-moi",
    "/ban/kinh-doanh",
    "/vai-tro",
    "/vai-tro/admin",
    "/module-registry",
    "/nhat-ky",
    "/cai-dat",
    "/brain",
    "/ho-so",
    "/doi-mat-khau",
    "/module/tasks",
    "/module/knowledge",
    "/module/tools",
    "/module/usage",
    "/module/approvals",
    "/doi-tac",
]

# Màn hình nhân viên được phép xem.
EMPLOYEE_SCREENS = [
    "/",
    "/brain",
    "/module/tasks",
    "/module/knowledge",
    "/module/usage",
    "/ho-so",
    "/doi-mat-khau",
]

ADMIN_PATHS_FOR_EMPLOYEE = [
    "/tai-khoan",
    "/tai-khoan/tao-moi",
    "/tai-khoan/nhan-vien-01",
    "/ban",
    "/vai-tro",
    "/phan-quyen",
    "/module-registry",
    "/nhat-ky",
    "/cai-dat",
    "/doi-tac",
    "/module/tools",
    "/module/approvals",
]


# --------------------------------------------------------------------------- HTML
class Page(HTMLParser):
    """Thu thập href, nav, form, landmark và dấu hiệu inline để kiểm tra."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.nav_items: list[dict] = []
        self.forms: list[dict] = []
        self.lang: str | None = None
        self.has_main = False
        self.h1 = 0
        self.tds = 0
        self.tds_no_label = 0
        self.ths = 0
        self.ths_no_scope = 0
        self.inline_scripts = 0
        self.inline_styles = 0
        self.inline_style_attrs = 0
        self.inline_handlers: list[tuple[str, str]] = []
        self._form: dict | None = None
        self._nav_stack: list[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        a = {k: (v if v is not None else "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "main":
            self.has_main = True
        if tag == "h1":
            self.h1 += 1
        if tag == "td":
            self.tds += 1
            if not a.get("data-label"):
                self.tds_no_label += 1
        if tag == "th":
            self.ths += 1
            if not a.get("scope"):
                self.ths_no_scope += 1
        if tag == "script" and not a.get("src"):
            self.inline_scripts += 1
        if tag == "style":
            self.inline_styles += 1
        for name in a:
            low = name.lower()
            if low == "style":
                self.inline_style_attrs += 1
            if low.startswith("on") and low not in {"one"}:
                self.inline_handlers.append((tag, low))
        if tag == "a":
            href = a.get("href")
            if href:
                self.hrefs.append(href)
            classes = (a.get("class") or "").split()
            if "nav-item" in classes:
                item = {"href": href or "", "active": "is-active" in classes, "text": ""}
                self.nav_items.append(item)
                self._nav_stack.append(item)
        if tag == "form":
            form = {
                "action": a.get("action") or "",
                "method": (a.get("method") or "get").lower(),
                "has_csrf": False,
                "csrf": None,
            }
            self.forms.append(form)
            self._form = form
        if tag == "input" and self._form is not None and a.get("name") == "_csrf":
            self._form["has_csrf"] = True
            self._form["csrf"] = a.get("value") or ""

    def handle_startendtag(self, tag: str, attrs) -> None:  # type: ignore[override]
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag == "a" and self._nav_stack:
            self._nav_stack.pop()
        if tag == "form":
            self._form = None

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._nav_stack:
            self._nav_stack[-1]["text"] += data


def parse_page(html: str) -> Page:
    p = Page()
    p.feed(html)
    p.close()
    return p


def csrf_value(html: str) -> str:
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    assert m, "Không tìm thấy input _csrf trong HTML"
    return m.group(1)


# ------------------------------------------------------------------- tài khoản
def seed_accounts() -> None:
    """Tạo 3 tài khoản thật trên DB tạm; mật khẩu chủ đọc từ secrets/."""
    conn = db.connect()
    try:
        has_owner = conn.execute("SELECT 1 FROM users WHERE id=?", (OWNER_ID,)).fetchone()
        services.tao_super_admin(conn, OWNER_ID, OWNER_PW, "Anh Thanh", reset=bool(has_owner))
        actor = auth.nguoi_dung_day_du(conn, OWNER_ID)
        perms = rbac.quyen_hieu_luc(conn, actor)
        accounts = [
            (ADMIN_ID, "Quản trị viên", "admin", "ban-dieu-hanh", ADMIN_PW),
            (EMPLOYEE_ID, "Nguyễn Văn Nhân", "employee", "kinh-doanh", EMPLOYEE_PW),
        ]
        for user_id, name, role, dept, password in accounts:
            if conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                continue
            services.tao_nguoi_dung(conn, actor, perms, {
                "id": user_id,
                "display_name": name,
                "email": f"{user_id}@vipgroup.com.vn",
                "role_code": role,
                "department_id": dept,
                "password": password,
                "must_change": "0",
                "scope_mode": "tenant",
                "scope_departments": [],
            })
    finally:
        conn.close()


@pytest.fixture()
def seeded(client):
    seed_accounts()
    return client


def login(client: TestClient, user_id: str, password: str) -> None:
    r = client.get("/dang-nhap")
    assert r.status_code == 200, f"Không tải được /dang-nhap: {r.status_code}"
    token = csrf_value(r.text)
    r = client.post(
        "/dang-nhap",
        data={"userId": user_id, "matKhau": password, "_csrf": token, "next": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303, f"Đăng nhập {user_id} thất bại: HTTP {r.status_code}"
    home = client.get("/")
    assert home.status_code == 200, f"Sau đăng nhập {user_id}, / trả HTTP {home.status_code}"


def module_routes() -> dict[str, str]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT code, route FROM modules WHERE status='active'").fetchall()
        return {r["code"]: r["route"] for r in rows}
    finally:
        conn.close()


def assert_page_contract(page: Page, path: str) -> None:
    """Hợp đồng HTML tối thiểu: landmark, ngôn ngữ, bảng có nhãn, không inline."""
    assert page.lang == "vi", f"{path}: thiếu <html lang='vi'>"
    assert page.has_main, f"{path}: thiếu landmark <main>"
    assert page.h1 >= 1, f"{path}: thiếu <h1>"
    assert page.inline_scripts == 0, f"{path}: có script inline (CSP chặt)"
    assert page.inline_styles == 0, f"{path}: có <style> inline"
    assert page.inline_style_attrs == 0, f"{path}: có thuộc tính style= inline"
    assert not page.inline_handlers, f"{path}: có handler inline {page.inline_handlers[:3]}"
    assert page.tds_no_label == 0, f"{path}: {page.tds_no_label} ô <td> thiếu data-label"
    assert page.ths_no_scope == 0, f"{path}: {page.ths_no_scope} ô <th> thiếu scope"


# ------------------------------------------------------------------------ test
def test_dang_nhap_ba_vai_tro_va_menu_theo_api_me(seeded):
    routes = module_routes()
    expected = {
        "super": {"dashboard", "brain", "tasks", "knowledge", "tools", "usage",
                  "approvals", "partner", "accounts", "departments", "roles",
                  "permissions", "modules", "audit", "settings"},
        "admin": {"dashboard", "brain", "tasks", "knowledge", "tools", "usage",
                  "approvals", "accounts", "departments", "roles", "permissions",
                  "modules", "audit"},
        "employee": {"dashboard", "brain", "tasks", "knowledge", "usage"},
    }

    def check(client: TestClient, user_id: str, password: str, kind: str) -> None:
        login(client, user_id, password)
        me = client.get("/api/me")
        assert me.status_code == 200
        data = me.json()["data"]
        assert data["id"] == user_id
        assert set(data["modules"]) == expected[kind], f"{kind}: module /api/me sai"

        home = client.get("/")
        page = parse_page(home.text)
        nav_routes = [item["href"] for item in page.nav_items]
        wanted = [routes[code] for code in data["modules"]]
        assert nav_routes == wanted, f"{kind}: menu không khớp /api/me"
        assert len(nav_routes) == len(me.json()["data"]["modules"])
        return page

    owner_page = check(seeded, OWNER_ID, OWNER_PW, "super")
    # Super Admin thấy đủ 15 module và mục đang mở đúng.
    assert len(owner_page.nav_items) == 15
    accounts = seeded.get("/tai-khoan")
    assert accounts.status_code == 200
    active = [i["href"] for i in parse_page(accounts.text).nav_items if i["active"]]
    assert active == ["/tai-khoan"], "Menu không đánh dấu mục Tài khoản đang mở"

    with TestClient(app) as admin_client:
        check(admin_client, ADMIN_ID, ADMIN_PW, "admin")

    with TestClient(app) as employee_client:
        page = check(employee_client, EMPLOYEE_ID, EMPLOYEE_PW, "employee")
        assert len(page.nav_items) == 5, "Nhân viên phải chỉ thấy đúng 5 module"
        labels = {re.sub(r"\s+", " ", item["text"]).strip() for item in page.nav_items}
        for hidden in ("Tài khoản", "Ban / Bộ phận", "Vai trò", "Nhật ký", "Cài đặt"):
            assert hidden not in labels, f"Nhân viên không được thấy menu {hidden!r}"
        hrefs = {item["href"] for item in page.nav_items}
        for route in ("/tai-khoan", "/ban", "/vai-tro", "/phan-quyen",
                      "/module-registry", "/nhat-ky", "/cai-dat", "/doi-tac"):
            assert route not in hrefs, f"Nhân viên không được thấy link {route}"

        # Truy cập thẳng các màn quản trị phải bị chặn bằng trang 403 HTML.
        for path in ADMIN_PATHS_FOR_EMPLOYEE:
            r = employee_client.get(path)
            assert r.status_code == 403, f"{path}: nhân viên phải nhận 403, thấy {r.status_code}"
            assert 'class="error-code">403' in r.text
            assert "Không đủ quyền" in r.text


def test_crawl_link_noi_bo_khong_co_404_500(seeded):
    routes = module_routes()
    link_status: dict[tuple[str, str], int] = {}
    checked_pages = 0
    checked_links = 0
    failures: list[str] = []

    def crawl(client: TestClient, path: str, status: int = 200) -> Page:
        nonlocal checked_pages, checked_links
        r = client.get(path)
        assert r.status_code == status, f"{path}: HTTP {r.status_code}"
        page = parse_page(r.text)
        assert_page_contract(page, path)
        checked_pages += 1
        for href in page.hrefs:
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            url = urljoin("http://testserver" + path, href)
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or parts.netloc != "testserver":
                continue
            if parts.path.startswith("/static/") or parts.path in ("/dang-xuat",):
                continue
            key = (client.cookies.get("cowork_session") or "anon", url)
            if key not in link_status:
                link_status[key] = client.get(url, follow_redirects=False).status_code
                checked_links += 1
            code = link_status[key]
            if code >= 400:
                failures.append(f"{path} → {href}: HTTP {code}")
        return page

    login(seeded, OWNER_ID, OWNER_PW)
    for path in OWNER_SCREENS:
        crawl(seeded, path)
    assert routes["dashboard"] == "/"

    # Trang 404 của owner (NotFound nghiệp vụ) và link trong đó.
    crawl(seeded, "/module/khong-ton-tai", status=404)

    with TestClient(app) as employee_client:
        login(employee_client, EMPLOYEE_ID, EMPLOYEE_PW)
        for path in EMPLOYEE_SCREENS:
            crawl(employee_client, path)
        crawl(employee_client, "/tai-khoan", status=403)
        crawl(employee_client, "/module/khong-ton-tai", status=404)

    assert not failures, "Link nội bộ trả lỗi:\n" + "\n".join(sorted(set(failures)))
    assert checked_pages >= len(OWNER_SCREENS) + len(EMPLOYEE_SCREENS) + 2
    assert checked_links >= 30, f"Chỉ crawl được {checked_links} link, cần >= 30"


def test_moi_form_post_deu_co_csrf(seeded):
    post_forms = 0
    pages_checked = 0

    def check_forms(client: TestClient, path: str, status: int = 200) -> None:
        nonlocal post_forms, pages_checked
        r = client.get(path)
        assert r.status_code == status, f"{path}: HTTP {r.status_code}"
        page = parse_page(r.text)
        pages_checked += 1
        for form in page.forms:
            if form["method"] != "post":
                continue
            post_forms += 1
            assert form["action"].startswith("/"), f"{path}: form POST action ngoài hệ thống"
            assert form["has_csrf"], f"{path}: form POST {form['action']} thiếu _csrf"
            assert form["csrf"] and len(form["csrf"]) >= 16, (
                f"{path}: form POST {form['action']} có _csrf rỗng/không hợp lệ")

    # Form đăng nhập của khách.
    anon = TestClient(app)
    with anon:
        r = anon.get("/dang-nhap")
        assert r.status_code == 200
        login_form = [f for f in parse_page(r.text).forms if f["method"] == "post"]
        assert login_form and login_form[0]["has_csrf"]

    login(seeded, OWNER_ID, OWNER_PW)
    for path in OWNER_SCREENS:
        check_forms(seeded, path)
    check_forms(seeded, "/module/khong-ton-tai", status=404)

    with TestClient(app) as employee_client:
        login(employee_client, EMPLOYEE_ID, EMPLOYEE_PW)
        for path in EMPLOYEE_SCREENS:
            check_forms(employee_client, path)
        check_forms(employee_client, "/tai-khoan", status=403)

    assert post_forms >= 15, f"Chỉ kiểm tra {post_forms} form POST"
    assert pages_checked >= len(OWNER_SCREENS) + len(EMPLOYEE_SCREENS) + 2


def test_csp_chat_va_khong_inline_trong_template(seeded):
    templates = ROOT / "cowork" / "templates"
    files = sorted(templates.rglob("*.html"))
    assert len(files) >= 25
    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text, re.I), (
            f"{rel}: có <script> inline")
        assert "<style" not in text.lower(), f"{rel}: có <style> inline"
        assert not re.search(r"\sstyle\s*=", text, re.I), f"{rel}: có style= inline"
        assert not re.search(r"\son[a-z]+\s*=", text, re.I), f"{rel}: có handler inline"

    login(seeded, OWNER_ID, OWNER_PW)
    for path, status in (("/", 200), ("/tai-khoan", 200),
                         ("/module/khong-ton-tai", 404)):
        r = seeded.get(path)
        assert r.status_code == status
        page = parse_page(r.text)
        assert page.inline_scripts == 0
        assert page.inline_styles == 0
        assert page.inline_style_attrs == 0
        assert not page.inline_handlers
        csp = r.headers.get("content-security-policy", "")
        for directive in ("default-src 'self'", "script-src 'self'", "style-src 'self'",
                          "frame-ancestors 'none'", "base-uri 'none'"):
            assert directive in csp, f"{path}: CSP thiếu {directive}"
        assert "unsafe-inline" not in csp, f"{path}: CSP chứa unsafe-inline"
        assert "unsafe-eval" not in csp, f"{path}: CSP chứa unsafe-eval"

    anon = TestClient(app)
    with anon:
        r = anon.get("/dang-nhap")
        page = parse_page(r.text)
        assert page.inline_scripts == 0
        assert page.inline_style_attrs == 0
        assert "unsafe-inline" not in r.headers.get("content-security-policy", "")


def test_trang_loi_403_404_render_dung_va_khong_link_chet(seeded):
    login(seeded, OWNER_ID, OWNER_PW)
    r = seeded.get("/module/khong-ton-tai")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("text/html")
    assert 'class="error-code">404' in r.text
    assert "Không tìm thấy" in r.text
    assert 'href="/ho-so"' in r.text
    assert_page_contract(parse_page(r.text), "/module/khong-ton-tai")

    r = seeded.get("/tai-khoan/khong-ton-tai")
    assert r.status_code == 404
    assert 'class="error-code">404' in r.text

    with TestClient(app) as employee_client:
        login(employee_client, EMPLOYEE_ID, EMPLOYEE_PW)
        r = employee_client.get("/tai-khoan")
        assert r.status_code == 403
        assert r.headers["content-type"].startswith("text/html")
        assert 'class="error-code">403' in r.text
        assert "Không đủ quyền" in r.text
        page = parse_page(r.text)
        assert_page_contract(page, "/tai-khoan")
        assert "/ho-so" in page.hrefs

        r = employee_client.get("/module/khong-ton-tai")
        assert r.status_code == 404
        assert 'class="error-code">404' in r.text
        page = parse_page(r.text)
        assert_page_contract(page, "/module/khong-ton-tai")
        # Nhân viên không có quyền accounts: trang 404 không được mời họ vào /tai-khoan.
        assert "/tai-khoan" not in page.hrefs
        for href in page.hrefs:
            if href.startswith("/"):
                assert employee_client.get(href, follow_redirects=False).status_code < 400


def test_route_khong_ton_tai_phai_tra_ve_trang_404_html(seeded):
    login(seeded, OWNER_ID, OWNER_PW)
    r = seeded.get("/khong-ton-tai-ag01")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("text/html"), (
        "Route không khớp đang trả JSON mặc định của FastAPI, không dùng 404.html")
    assert 'class="error-code">404' in r.text
