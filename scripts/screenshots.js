/* Chụp ảnh các màn hình COWORK bằng Playwright (headless).
   Chạy: NODE_PATH=~/code/veh4-g12-playwright/node_modules \
         COWORK_OWNER_PASSWORD=... node scripts/screenshots.js */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.COWORK_BASE || "http://127.0.0.1:8899";
const PW = process.env.COWORK_OWNER_PASSWORD;
const OUT = path.join(__dirname, "..", "evidence", "screens");

(async () => {
  if (!PW) { console.error("Thiếu COWORK_OWNER_PASSWORD"); process.exit(2); }
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: "vi-VN" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("requestfailed", (r) => errors.push("requestfailed: " + r.url()));

  async function shot(name, url, full = true) {
    await page.goto(BASE + url, { waitUntil: "networkidle" });
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(OUT, name + ".png"), fullPage: full });
    console.log("shot", name, "→", url);
  }

  await page.goto(BASE + "/dang-nhap", { waitUntil: "networkidle" });
  await page.screenshot({ path: path.join(OUT, "00-login.png"), fullPage: true });
  await page.fill('input[name="userId"]', "anh-thanh");
  await page.fill('input[name="matKhau"]', PW);
  await Promise.all([page.waitForURL(BASE + "/"), page.click('button[type="submit"]')]);

  const pages = [
    ["01-dashboard", "/"],
    ["02-accounts", "/tai-khoan"],
    ["03-account-create", "/tai-khoan/tao-moi"],
    ["04-account-detail", "/tai-khoan/nhan-vien-01"],
    ["05-account-permissions", "/tai-khoan/nhan-vien-01/phan-quyen"],
    ["06-departments", "/ban"],
    ["07-department-detail", "/ban/kinh-doanh"],
    ["08-roles", "/vai-tro"],
    ["09-role-admin", "/vai-tro/admin"],
    ["10-modules", "/module-registry"],
    ["11-audit", "/nhat-ky"],
    ["12-settings", "/cai-dat"],
    ["13-brain", "/brain"],
    ["14-profile", "/ho-so"],
    ["15-module-task", "/module/tasks"],
  ];
  for (const [name, url] of pages) await shot(name, url);

  const mob = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "vi-VN" });
  const mp = await mob.newPage();
  await mp.goto(BASE + "/dang-nhap", { waitUntil: "networkidle" });
  await mp.fill('input[name="userId"]', "anh-thanh");
  await mp.fill('input[name="matKhau"]', PW);
  await Promise.all([mp.waitForURL(BASE + "/"), mp.click('button[type="submit"]')]);
  await mp.screenshot({ path: path.join(OUT, "20-mobile-dashboard.png"), fullPage: true });
  await mp.goto(BASE + "/tai-khoan", { waitUntil: "networkidle" });
  await mp.screenshot({ path: path.join(OUT, "21-mobile-accounts.png"), fullPage: true });

  console.log("ERRORS:", errors.length ? errors.join("\n") : "none");
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
