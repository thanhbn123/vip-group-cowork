/* AG-01 FRONTEND — chụp bằng chứng giao diện COWORK bằng Playwright + Chrome hệ thống.
   Chạy:
     NODE_PATH="$HOME/code/veh4-g12-playwright/node_modules" \
     COWORK_OWNER_PASSWORD="$(cat secrets/owner-anh-thanh.txt)" \
     node evidence/AG01-capture.js
   Kết quả: evidence/AG01-screens/*.png + evidence/AG01-screens/report.json
   Không ghi mật khẩu vào ảnh/report. */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.COWORK_BASE || "http://127.0.0.1:8899";
const PW = process.env.COWORK_OWNER_PASSWORD;
const OUT = path.join(__dirname, "AG01-screens");
const DESKTOP = { width: 1440, height: 1000 };
const MOBILE = { width: 390, height: 844 };

const PAGES = [
  ["01-dashboard", "/", "owner"],
  ["02-accounts", "/tai-khoan", "owner"],
  ["03-account-create", "/tai-khoan/tao-moi", "owner"],
  ["04-account-detail", "/tai-khoan/nhan-vien-01", "owner"],
  ["05-account-permissions", "/tai-khoan/nhan-vien-01/phan-quyen", "owner"],
  ["06-permissions-overview", "/phan-quyen", "owner"],
  ["07-departments", "/ban", "owner"],
  ["08-department-detail", "/ban/kinh-doanh", "owner"],
  ["09-roles", "/vai-tro", "owner"],
  ["10-role-admin", "/vai-tro/admin", "owner"],
  ["11-modules", "/module-registry", "owner"],
  ["12-audit", "/nhat-ky", "owner"],
  ["13-settings", "/cai-dat", "owner"],
  ["14-brain", "/brain", "owner"],
  ["15-profile", "/ho-so", "owner"],
  ["16-change-password", "/doi-mat-khau", "owner"],
  ["17-module-tasks", "/module/tasks", "owner"],
  ["18-module-knowledge", "/module/knowledge", "owner"],
  ["19-module-tools", "/module/tools", "owner"],
  ["20-module-usage", "/module/usage", "owner"],
  ["21-module-approvals", "/module/approvals", "owner"],
  ["22-partner", "/doi-tac", "owner"],
  ["23-error-404", "/module/khong-ton-tai", "owner", 404],
  ["24-employee-dashboard", "/", "employee"],
  ["25-employee-nav-module", "/module/tasks", "employee"],
  ["26-error-403", "/tai-khoan", "employee", 403],
  ["27-admin-dashboard", "/", "admin"],
];

const USERS = {
  owner: { id: "anh-thanh", pw: PW },
  employee: { id: "nhan-vien-01", pw: "Nv01!Passw0rd" },
  admin: { id: "quan-tri-01", pw: "Qt01!Passw0rd" },
};

function fileSafe(s) {
  return s.replace(/[^a-z0-9-]+/gi, "-").replace(/^-+|-+$/g, "");
}

async function login(browser, viewport, who) {
  const ctx = await browser.newContext({ viewport, locale: "vi-VN" });
  const page = await ctx.newPage();
  const u = USERS[who];
  await page.goto(BASE + "/dang-nhap", { waitUntil: "networkidle" });
  await page.fill('input[name="userId"]', u.id);
  await page.fill('input[name="matKhau"]', u.pw);
  await Promise.all([page.waitForURL(BASE + "/"), page.click('button[type="submit"]')]);
  return { ctx, page };
}

async function measure(page) {
  return page.evaluate(() => {
    const vw = window.innerWidth;
    const de = document.documentElement;
    const overflow = de.scrollWidth > vw + 1;
    const bad = [];
    if (overflow) {
      document.querySelectorAll("body *").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && r.right > vw + 1) {
          const cls = typeof el.className === "string" ? el.className.split(/\s+/).slice(0, 2).join(".") : "";
          bad.push({
            tag: el.tagName.toLowerCase(),
            cls,
            id: el.id || "",
            right: Math.round(r.right),
            width: Math.round(r.width),
            text: (el.textContent || "").trim().slice(0, 60),
          });
        }
      });
    }
    // Trường nhập thiếu tên truy cập (label / aria-label / title).
    const noName = [];
    document.querySelectorAll("input:not([type=hidden]), select, textarea").forEach((el) => {
      const id = el.getAttribute("id");
      const hasLabel =
        !!(el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.getAttribute("title")) ||
        !!el.closest("label") ||
        !!(id && document.querySelector('label[for="' + CSS.escape(id) + '"]'));
      if (!hasLabel) {
        noName.push({ tag: el.tagName.toLowerCase(), type: el.getAttribute("type") || "", name: el.getAttribute("name") || "" });
      }
    });
    // Phần tử [hidden] nhưng CSS vẫn hiển thị (lỗi display đè hidden).
    const hiddenVisible = [];
    document.querySelectorAll("[hidden]").forEach((el) => {
      const style = getComputedStyle(el);
      if (style.display !== "none") {
        const cls = typeof el.className === "string" ? el.className.split(/\s+/).slice(0, 2).join(".") : "";
        hiddenVisible.push({ tag: el.tagName.toLowerCase(), cls });
      }
    });
    const tdNoLabel = document.querySelectorAll("td:not([data-label])").length;
    const thNoScope = document.querySelectorAll("th:not([scope])").length;
    // Nút / liên kết không có tên.
    const noLabelBtn = [];
    document.querySelectorAll("button, a[href]").forEach((el) => {
      const txt = (el.textContent || "").trim();
      const aria = el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.getAttribute("title");
      if (!txt && !aria) {
        const cls = typeof el.className === "string" ? el.className.split(/\s+/).slice(0, 2).join(".") : "";
        noLabelBtn.push({ tag: el.tagName.toLowerCase(), cls, href: el.getAttribute("href") || "" });
      }
    });
    // Ảnh / SVG thiếu alt hoặc aria-hidden.
    const svgNoA11y = [];
    document.querySelectorAll("img, svg").forEach((el) => {
      if (el.tagName === "IMG" && !el.hasAttribute("alt")) svgNoA11y.push("img");
      if (el.tagName.toLowerCase() === "svg" && el.getAttribute("aria-hidden") !== "true" &&
          !el.getAttribute("aria-label") && !el.querySelector("title")) svgNoA11y.push("svg");
    });
    return {
      viewport: vw,
      scrollWidth: de.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      overflow,
      offenders: bad.slice(0, 12),
      inputsNoName: noName,
      hiddenVisible,
      tdNoLabel,
      thNoScope,
      controlsNoName: noLabelBtn,
      svgNoA11yCount: svgNoA11y.length,
    };
  });
}

(async () => {
  if (!PW) {
    console.error("Thiếu COWORK_OWNER_PASSWORD");
    process.exit(2);
  }
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  const report = { base: BASE, generatedAt: new Date().toISOString(), screens: [], errors: [] };

  for (const viewport of [{ name: "desktop", size: DESKTOP }, { name: "mobile", size: MOBILE }]) {
    const sessions = {};
    for (const who of ["owner", "employee", "admin"]) {
      sessions[who] = await login(browser, viewport.size, who);
    }
    for (const [name, url, who, expectStatus] of PAGES) {
      const { page } = sessions[who];
      const consoleErrors = [];
      const onConsole = (m) => { if (m.type() === "error") consoleErrors.push("console: " + m.text()); };
      const onPageError = (e) => consoleErrors.push("pageerror: " + e.message);
      const onRequestFailed = (r) => consoleErrors.push("requestfailed: " + r.url());
      page.on("console", onConsole);
      page.on("pageerror", onPageError);
      page.on("requestfailed", onRequestFailed);
      let resp;
      try {
        resp = await page.goto(BASE + url, { waitUntil: "networkidle" });
        await page.waitForTimeout(150);
        await page.screenshot({ path: path.join(OUT, `${viewport.name}-${name}.png`), fullPage: true });
        const metrics = await measure(page);
        const row = {
          viewport: viewport.name,
          name,
          url,
          who,
          status: resp ? resp.status() : null,
          ...metrics,
          consoleErrors,
        };
        report.screens.push(row);
        if (row.overflow) report.errors.push(`${viewport.name} ${name} (${url}): tràn ngang ${row.scrollWidth}>${row.viewport}`);
        if (row.hiddenVisible.length) report.errors.push(`${viewport.name} ${name}: [hidden] vẫn hiển thị ${JSON.stringify(row.hiddenVisible)}`);
        if (row.tdNoLabel) report.errors.push(`${viewport.name} ${name}: ${row.tdNoLabel} td thiếu data-label`);
        if (row.thNoScope) report.errors.push(`${viewport.name} ${name}: ${row.thNoScope} th thiếu scope`);
        const statusOk = expectStatus ? row.status === expectStatus : row.status === 200;
        if (!statusOk) report.errors.push(`${viewport.name} ${name} (${url}): HTTP ${row.status} (mong đợi ${expectStatus || 200})`);
        const consoleUnexpected = consoleErrors.filter((e) => !(expectStatus && /Failed to load resource/.test(e)));
        if (consoleUnexpected.length) report.errors.push(`${viewport.name} ${name}: ${consoleUnexpected.join(" | ")}`);
        console.log(`[${viewport.name}] ${name} ${url} → ${row.status} · overflow=${row.overflow} · console=${consoleErrors.length}`);
      } finally {
        page.off("console", onConsole);
        page.off("pageerror", onPageError);
        page.off("requestfailed", onRequestFailed);
      }
    }
    for (const who of Object.keys(sessions)) await sessions[who].ctx.close();
  }

  // Trang đăng nhập (không phiên) — chụp riêng.
  for (const vp of [{ name: "desktop", size: DESKTOP }, { name: "mobile", size: MOBILE }]) {
    const ctx = await browser.newContext({ viewport: vp.size, locale: "vi-VN" });
    const page = await ctx.newPage();
    const resp = await page.goto(BASE + "/dang-nhap", { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(OUT, `${vp.name}-00-login.png`), fullPage: true });
    const metrics = await measure(page);
    report.screens.push({ viewport: vp.name, name: "00-login", url: "/dang-nhap", who: "anon",
                          status: resp.status(), ...metrics, consoleErrors: [] });
    await ctx.close();
  }

  // Menu mobile: kiểm tra trạng thái inert và chụp màn hình mở menu.
  {
    const { ctx, page } = await login(browser, MOBILE, "employee");
    const closedInert = await page.evaluate(() => {
      const sb = document.getElementById("sidebar");
      return sb ? sb.hasAttribute("inert") : null;
    });
    await page.click("[data-toggle-sidebar]");
    await page.waitForTimeout(200);
    const opened = await page.evaluate(() => {
      const sb = document.getElementById("sidebar");
      const tg = document.querySelector("[data-toggle-sidebar]");
      return {
        inert: sb ? sb.hasAttribute("inert") : null,
        expanded: tg ? tg.getAttribute("aria-expanded") : null,
        focusInSidebar: !!(sb && sb.contains(document.activeElement)),
      };
    });
    await page.screenshot({ path: path.join(OUT, "mobile-28-nav-open.png"), fullPage: false });
    report.navDrawer = { closedInert, opened };
    if (!closedInert) report.errors.push("mobile nav: sidebar không inert khi đóng");
    if (opened.inert !== false || opened.expanded !== "true") report.errors.push("mobile nav: trạng thái mở không đúng");
    await ctx.close();
  }

  report.screenCount = report.screens.length;
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2));
  console.log(`\nĐã chụp ${report.screens.length} ảnh → ${OUT}`);
  if (report.errors.length) {
    console.log("CẢNH BÁO:\n" + report.errors.join("\n"));
    process.exitCode = 3;
  } else {
    console.log("Không phát hiện tràn ngang / lỗi console / HTTP lỗi.");
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
