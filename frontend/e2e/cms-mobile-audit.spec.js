const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const fs = require("node:fs/promises");
const path = require("node:path");
const { login } = require("./helpers");

const widths = (process.env.CMS_AUDIT_WIDTHS || "390").split(",").map(Number);
const types = ["hero", "announcement", "banner", "story", "page", "faq_item", "nav_item", "footer_group", "footer_item", "footer_text", "homepage_section", "department_visual"];
for (const width of widths) test(`CMS pages and editor states at ${width}px`, async ({ page, context }, testInfo) => {
  test.setTimeout(300000);
  page.setDefaultTimeout(15000);
  await page.setViewportSize({ width, height: 844 });
  const output = process.env.CMS_AUDIT_OUTPUT ? path.join(process.env.CMS_AUDIT_OUTPUT, String(width)) : testInfo.outputPath("pages");
  await fs.mkdir(output, { recursive: true });
  const results = [], errors = [];
  page.on("pageerror", error => errors.push(String(error)));
  page.on("dialog", dialog => dialog.accept());
  async function capture(name, url, action) {
    await page.goto(url, { waitUntil: "networkidle", timeout: 20000 });
    await expect(page.getByRole("heading", { name: "Sedang offline", exact: true })).not.toBeVisible();
    if (name.startsWith("product-edit-")) await page.getByTestId("admin-product-editor").waitFor({ state: "visible", timeout: 15000 });
    if (action) { await action(); await page.waitForTimeout(200); }
    await page.screenshot({ path: path.join(output, name + ".png"), fullPage: true });
    const metrics = await page.evaluate(() => ({
      width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      brokenImages: [...document.images].filter(img => img.complete && img.currentSrc && !img.naturalWidth).map(img => img.currentSrc),
    }));
    const violations = width === 390 ? (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()).violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => ({ target: n.target, summary: n.failureSummary })) })) : [];
    results.push({ name, url, ...metrics, violations });
    await fs.writeFile(path.join(output, "report.json"), JSON.stringify({ results, errors }, null, 2));
    console.log(`${width}px ${name}: overflow=${metrics.scrollWidth > width}, violations=${violations.length}`);
  }
  for (const [name, url] of [["login", "/admin/"], ["forgot-password", "/admin/forgot-password"], ["reset-password", "/admin/reset-password"]]) await capture(name, url);
  await login(context);
  const productRows = (await (await context.request.get("/api/v1/admin/products?page_size=100")).json()).items;
  const products = await Promise.all(productRows.map(async item => (await (await context.request.get("/api/v1/admin/products/" + item.id)).json())));
  const contentsResponse = await (await context.request.get("/api/v1/admin/cms/content")).json();
  const contents = contentsResponse.items || contentsResponse;
  const media = await (await context.request.get("/api/v1/admin/cms/media")).json();
  if (!media.items.length) {
    const csrf = (await context.cookies()).find(cookie => cookie.name === "csrf_token")?.value;
    const upload = await context.request.post("/api/v1/admin/cms/media", {
      headers: { "X-CSRF-Token": csrf },
      multipart: { file: { name: "mobile-audit.png", mimeType: "image/png", buffer: await fs.readFile(path.join(__dirname, "../public/pwa/icon-192.png")) } },
    });
    expect(upload.ok()).toBeTruthy();
  }
  const routes = [
    ["dashboard", "/admin/"], ["products", "/admin/products"], ["product-new", "/admin/products/new"], ["categories", "/admin/categories"],
    ["orders", "/admin/orders"], ["orders-payment", "/admin/orders?stage=payment"], ["orders-archived", "/admin/orders?stage=archived"],
    ["telegram-inbox", "/admin/telegram-inbox"], ["telegram-thread", "/admin/telegram-inbox?conversation=" + "a".repeat(32)],
    ["customers", "/admin/customers"], ["cms", "/admin/cms"], ["cms-all", "/admin/cms?view=all"], ["cms-homepage", "/admin/cms/homepage"], ["cms-stories", "/admin/cms/stories"],
    ["cms-help", "/admin/cms/help"], ["cms-navigation", "/admin/cms/navigation"], ["media", "/admin/media"], ["settings", "/admin/settings"],
    ["inquiry-detail", "/admin/orders/inquiry/SC-" + "C".repeat(32)],
  ];
  for (let index = 1; index <= 7; index++) routes.push(["order-stage-" + index, "/admin/orders/MOBILE-AUDIT-" + index]);
  for (const type of types) {
    const entry = contents.find(item => item.content_type === type);
    routes.push(["cms-edit-" + type, entry ? "/admin/cms/" + entry.id : "/admin/cms/new?type=" + type]);
  }
  for (const type of new Set(products.map(item => item.product_type))) routes.push(["product-edit-" + type, "/admin/products/" + products.find(item => item.product_type === type).id]);
  for (const [name, url] of routes) await capture(name, url);
  await capture("category-editor", "/admin/categories", () => page.getByTestId("catalog-add-department").click());
  await capture("payment-editor", "/admin/settings", () => page.getByTestId("add-payment-destination").click());
  await capture("customer-detail", "/admin/customers", () => width < 768 ? page.getByText("Detail", { exact: true }).filter({ visible: true }).first().click() : page.locator('[data-testid^="customer-row-"]').first().getByRole("button").click());
  await capture("media-editor", "/admin/media", () => page.locator('[data-testid^="media-item-"]').first().click());
  const hero = contents.find(item => item.content_type === "hero");
  await capture("cms-media-picker", hero ? "/admin/cms/" + hero.id : "/admin/cms/new?type=hero", () => page.getByTestId("cms-media-choose").click());
  await capture("cms-editor-ru", hero ? "/admin/cms/" + hero.id : "/admin/cms/new?type=hero", () => page.getByTestId("cms-locale-ru").click());
  await capture("product-editor-ru", "/admin/products/" + products[0].id, () => page.getByTestId("editor-locale-ru").click());
  if (width < 1024) {
    await capture("navigation-drawer", "/admin/", () => page.getByTestId("admin-menu-open").click());
    await capture("telegram-product-panel", "/admin/telegram-inbox?conversation=" + "a".repeat(32), () => page.getByRole("button", { name: "Cari produk / Pending Order" }).click());
  }
  await fs.writeFile(path.join(output, "report.json"), JSON.stringify({ results, errors }, null, 2));
  await testInfo.attach("audit-report", { path: path.join(output, "report.json"), contentType: "application/json" });
  expect(errors).toEqual([]);
  expect(results.filter(item => item.scrollWidth > width), "Page overflow").toEqual([]);
  expect(results.filter(item => item.brokenImages.length), "Broken images").toEqual([]);
  expect(results.flatMap(item => item.violations.filter(v => ["serious", "critical"].includes(v.impact)).map(v => ({ page: item.name, ...v }))), "Accessibility issues").toEqual([]);
});
