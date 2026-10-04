const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");
const conversation = "a".repeat(32);
test.beforeEach(async ({ context }) => login(context));

test("restoring an admin session loads categories and product editor without stranded skeletons", async ({ page, context }) => {
  await page.goto("/admin/categories");
  await expect(page.getByTestId("catalog-add-department")).toBeVisible();
  const products = await (await context.request.get("/api/v1/admin/products")).json();
  await page.goto("/admin/products/" + products.items[0].id);
  await expect(page.getByTestId("admin-product-editor")).toBeVisible();
  await expect(page.getByTestId("editor-brand")).toBeVisible();
});

test("notification deep link opens the selected chat, order links stay inside the installed app", async ({ page }) => {
  await page.goto("/admin/telegram-inbox?conversation=" + conversation);
  await expect(page.getByTestId("telegram-inbox-thread")).toBeVisible();
  await expect(page.getByTestId("telegram-inbox-composer")).toBeVisible();
  const links = page.getByTestId("telegram-conversation-orders").locator("a");
  await expect(links.first()).toBeVisible();
  const href = await links.first().getAttribute("href");
  expect(href).toMatch(/^\/admin\/orders\//);
  expect(href).not.toContain("/admin/admin/");
  await links.first().click();
  await expect(page.getByTestId("admin-order-detail")).toBeVisible();
});

test("mobile back navigation discards the previous chat draft and product panel can close", async ({ page }) => {
  await page.goto("/admin/telegram-inbox?conversation=" + conversation);
  const input = page.getByTestId("telegram-inbox-message-input");
  await input.fill("Draft only for this customer");
  await page.getByRole("button", { name: "Kembali ke daftar chat", exact: true }).click();
  await expect(page).not.toHaveURL(/conversation=/);
  await page.getByTestId("telegram-conversation-" + conversation).click();
  await expect(input).toHaveValue("");
  await page.getByRole("button", { name: "Cari produk / Pending Order" }).click();
  const panel = page.getByRole("dialog", { name: "Panel produk dan Pending Order" });
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "Tutup panel produk" }).click();
  await expect(panel).not.toBeVisible();
});

test("drawer traps focus, closes with Escape and restores the menu button", async ({ page }) => {
  await page.goto("/admin/");
  const trigger = page.getByTestId("admin-menu-open");
  await trigger.click();
  await expect(page.getByRole("dialog", { name: "Navigasi CMS" })).toBeVisible();
  for (let index = 0; index < 20; index++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => Boolean(document.activeElement.closest('[role="dialog"]')))).toBeTruthy();
  }
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("admin-drawer")).not.toBeVisible();
  await expect(trigger).toBeFocused();
});

test("keyboard-sized viewport keeps chat composer visible and scrollable", async ({ page }) => {
  await page.goto("/admin/telegram-inbox?conversation=" + conversation);
  await expect(page.getByTestId("telegram-inbox-message-input")).toBeVisible();
  await page.setViewportSize({ width: 360, height: 420 });
  await page.getByTestId("telegram-inbox-message-input").focus();
  const composer = await page.getByTestId("telegram-inbox-composer").boundingBox();
  expect(composer.y + composer.height).toBeLessThanOrEqual(422);
  const messages = await page.getByTestId("telegram-inbox-messages").boundingBox();
  expect(messages.height).toBeGreaterThan(40);
});

test("a ten-product Telegram carousel keeps all touch controls within a narrow screen", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await page.route("**/api/v1/admin/telegram-inbox/" + conversation, async route => {
    const response = await route.fetch();
    const detail = await response.json();
    detail.messages = [{ id: "mobile-long-carousel", direction: "outbound", type: "rich", text: "", created_at: "2026-10-04T00:00:00Z", rich_content: {
      title: "Keranjang sepuluh produk", slides: Array.from({ length: 10 }, (_, index) => ({ caption: "Produk " + (index + 1), image_url: null })),
    } }];
    await route.fulfill({ response, json: detail });
  });
  await page.goto("/admin/telegram-inbox?conversation=" + conversation);
  const carousel = page.getByTestId("telegram-cart-carousel");
  await expect(carousel).toBeVisible();
  const controls = carousel.getByRole("button", { name: /^Tampilkan produk / });
  await expect(controls).toHaveCount(10);
  const bounds = await carousel.boundingBox();
  for (const control of await controls.all()) {
    const box = await control.boundingBox();
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.x).toBeGreaterThanOrEqual(bounds.x);
    expect(box.x + box.width).toBeLessThanOrEqual(bounds.x + bounds.width + 1);
  }
  await controls.last().click();
  await expect(carousel).toContainText("Produk 10");
  await page.screenshot({ path: testInfo.outputPath("ten-product-carousel.png"), fullPage: true });
});

test("mobile product dialog traps focus and closes when switching to desktop", async ({ page }) => {
  await page.goto("/admin/telegram-inbox?conversation=" + conversation);
  await page.getByRole("button", { name: "Cari produk / Pending Order" }).click();
  const dialog = page.getByRole("dialog", { name: "Panel produk dan Pending Order" });
  await expect(dialog).toBeVisible();
  for (let index = 0; index < 12; index++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => Boolean(document.activeElement.closest('[role="dialog"]')))).toBeTruthy();
  }
  await page.setViewportSize({ width: 1280, height: 844 });
  await expect(dialog).not.toBeVisible();
  await expect(page.getByTestId("telegram-inbox-thread")).not.toHaveAttribute("aria-hidden", "true");
});

test("a logged-out notification link returns to the chat after real admin login", async ({ page, context }) => {
  await context.clearCookies();
  await page.goto("/admin/telegram-inbox?conversation=" + conversation);
  await page.getByTestId("admin-login-email").fill(process.env.CMS_ADMIN_EMAIL || "operator@example.com");
  await page.getByTestId("admin-login-password").fill(process.env.CMS_ADMIN_PASSWORD || "AdminPass123!");
  await page.getByTestId("admin-login-submit").click();
  await expect(page).toHaveURL(new RegExp("conversation=" + conversation));
  await expect(page.getByTestId("telegram-inbox-composer")).toBeVisible();
});
