const { test, expect } = require("@playwright/test");
const { createECDH } = require("node:crypto");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { login } = require("./helpers");
const key = createECDH("prime256v1"); key.generateKeys();
const publicKey = key.getPublicKey().toString("base64url");

test.beforeEach(async ({ context }) => login(context));

test("native Chromium validates installation requirements in a regular browser profile", async ({ playwright, baseURL }) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "cms-installability-"));
  const context = await playwright.chromium.launchPersistentContext(directory, { headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined, args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  try {
    const page = context.pages()[0];
    await page.goto(baseURL + "/admin/", { waitUntil: "networkidle" });
    const session = await context.newCDPSession(page);
    const result = await session.send("Page.getInstallabilityErrors");
    expect(result.installabilityErrors).toEqual([]);
  } finally {
    await context.close();
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test("manifest, service-worker scope, icons and private-cache boundary are correct", async ({ page, context, baseURL }) => {
  await page.goto("/admin/settings");
  await expect(page.getByTestId("cms-device-settings")).toBeVisible();
  const manifest = await (await context.request.get("/admin/manifest.webmanifest")).json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.scope).toBe("/admin/");
  expect(new URL(manifest.start_url, baseURL).pathname).toBe("/admin/");
  for (const icon of manifest.icons) {
    const response = await context.request.get(icon.src);
    expect(response.headers()["content-type"]).toContain("image/png");
    expect(response.ok()).toBeTruthy();
  }
  const workerResponse = await context.request.get("/admin/cms-sw.js");
  expect(workerResponse.headers()["content-type"]).toMatch(/javascript/);
  expect(workerResponse.headers()["service-worker-allowed"]).toBe("/admin/");
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL)).toContain("/admin/cms-sw.js");
  expect(await page.evaluate(async () => (await navigator.serviceWorker.ready).scope)).toBe(baseURL + "/admin/");
  const cacheUrls = await page.evaluate(async () => {
    const cache = await caches.open("cantik-cms-offline-v1");
    return (await cache.keys()).map(request => new URL(request.url).pathname);
  });
  expect(cacheUrls).toEqual(["/admin/offline.html"]);
  expect(await page.getByTestId("admin-nav-dashboard").getAttribute("href")).toBe("/admin/");
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sedang offline" })).toBeVisible();
  await context.setOffline(false);
  await page.getByRole("button", { name: "Coba lagi" }).click();
  await expect(page.getByTestId("cms-device-settings")).toBeVisible();
});

test("install button uses the browser prompt and reports installed only after appinstalled", async ({ page }) => {
  await page.goto("/admin/settings");
  await expect(page.getByTestId("cms-install")).toBeVisible();
  await page.evaluate(() => {
    window.__installCalls = 0;
    const event = new Event("beforeinstallprompt", { cancelable: true });
    event.prompt = async () => { window.__installCalls++; };
    event.userChoice = Promise.resolve({ outcome: "accepted" });
    window.dispatchEvent(event);
  });
  await page.getByTestId("cms-install").click();
  expect(await page.evaluate(() => window.__installCalls)).toBe(1);
  await expect(page.getByText("Pemasangan dikonfirmasi", { exact: false })).toBeVisible();
  await expect(page.getByTestId("cms-install")).toHaveText("Install ke Android");
  await page.evaluate(() => window.dispatchEvent(new Event("appinstalled")));
  await expect(page.getByTestId("cms-install")).toHaveText("CMS sudah terpasang");
  await expect(page.getByTestId("cms-install")).toBeDisabled();
});

test("dismissed install does not claim success and unavailable prompt gives Android instructions", async ({ page }) => {
  await page.goto("/admin/settings");
  await expect(page.getByTestId("cms-install")).toBeVisible();
  await page.evaluate(() => {
    const event = new Event("beforeinstallprompt", { cancelable: true });
    event.prompt = async () => {};
    event.userChoice = Promise.resolve({ outcome: "dismissed" });
    window.dispatchEvent(event);
  });
  await page.getByTestId("cms-install").click();
  await expect(page.getByText("Pemasangan dibatalkan.", { exact: false })).toBeVisible();
  await page.getByTestId("cms-install").click();
  await expect(page.getByTestId("cms-install-help")).toContainText("Chrome Android");
});

test("per-device permission, subscribe, test notification and unsubscribe complete", async ({ page }) => {
  const requests = [];
  await page.route("**/api/v1/admin/push/**", async route => {
    requests.push({ path: new URL(route.request().url()).pathname, method: route.request().method(), data: route.request().postDataJSON() });
    await route.fulfill({ json: route.request().url().endsWith("/config") ? { enabled: true, public_key: publicKey } : { enabled: true, queued: true } });
  });
  await page.addInitScript(({ publicKey }) => {
    let permission = "default", subscription = null;
    Object.defineProperty(Notification, "permission", { get: () => permission });
    Notification.requestPermission = async () => { permission = "granted"; return permission; };
    PushManager.prototype.getSubscription = async () => subscription;
    PushManager.prototype.subscribe = async options => {
      subscription = {
        endpoint: "https://fcm.googleapis.com/fcm/send/browser-device-test", options,
        toJSON: () => ({ endpoint: "https://fcm.googleapis.com/fcm/send/browser-device-test", keys: { p256dh: publicKey, auth: "YWFhYWFhYWFhYWFhYWFhYQ" } }),
        unsubscribe: async () => { subscription = null; return true; },
      };
      return subscription;
    };
  }, { publicKey });
  await page.goto("/admin/settings");
  await expect(page.getByTestId("cms-push-enable")).toBeEnabled();
  await page.getByTestId("cms-push-enable").click();
  await expect(page.getByTestId("cms-push-status")).toHaveText("Notifikasi aktif di perangkat ini");
  expect(requests.some(request => request.method === "POST" && request.path.endsWith("/subscriptions"))).toBeTruthy();
  await page.getByTestId("cms-push-test").click();
  await expect(page.getByText("Notifikasi tes masuk antrean", { exact: false })).toBeVisible();
  expect(requests.some(request => request.path.endsWith("/test"))).toBeTruthy();
  await page.getByTestId("cms-push-disable").click();
  await expect(page.getByTestId("cms-push-status")).toHaveText("Notifikasi belum diaktifkan");
  expect(requests.some(request => request.method === "DELETE" && request.data.endpoint.endsWith("browser-device-test"))).toBeTruthy();
});

test("denied notification permission is explained and never reports enabled", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(Notification, "permission", { get: () => "denied" }));
  await page.route("**/api/v1/admin/push/config", route => route.fulfill({ json: { enabled: true, public_key: publicKey } }));
  await page.goto("/admin/settings");
  await expect(page.getByTestId("cms-push-status")).toHaveText("Izin notifikasi diblokir");
  await expect(page.getByTestId("cms-push-enable")).toBeDisabled();
});

// Chromium 145 headless reports Notification.permission as denied, and its
// service worker refuses showNotification, even after CDP grants permission.
// Run this suite in a virtual display to exercise the actual notification API.
test("native Chromium service worker displays a Telegram push while page is in background", async ({ page, context, baseURL }) => {
  await context.grantPermissions(["notifications"], { origin: new URL(baseURL).origin });
  const deviceAcks = [];
  context.on("request", request => {
    if (new URL(request.url()).pathname === "/api/v1/admin/push/delivery-ack" && request.method() === "POST") {
      try { deviceAcks.push(request.postDataJSON()); } catch { /* Invalid test requests remain visible as missing stages. */ }
    }
  });
  const session = await context.newCDPSession(page);
  let registrationId;
  let activated = false;
  const workerErrors = [];
  session.on("ServiceWorker.workerRegistrationUpdated", ({ registrations }) => {
    const registration = registrations.find(item => item.scopeURL === baseURL + "/admin/");
    if (registration) registrationId = registration.registrationId;
  });
  session.on("ServiceWorker.workerVersionUpdated", ({ versions }) => {
    activated = versions.some(item => item.scriptURL === baseURL + "/admin/cms-sw.js" && item.status === "activated");
  });
  session.on("ServiceWorker.workerErrorReported", error => workerErrors.push(error));
  await session.send("ServiceWorker.enable");
  await page.goto("/admin/settings");
  await expect.poll(() => registrationId).toBeTruthy();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL)).toContain("/admin/cms-sw.js");
  await expect.poll(() => activated).toBeTruthy();
  expect(await page.evaluate(() => Notification.permission)).toBe("granted");
  await page.evaluate(async () => (await navigator.serviceWorker.ready).showNotification("Notifikasi browser", { tag: "notification-preflight" }));
  await expect.poll(() => page.evaluate(async () => (await (await navigator.serviceWorker.ready).getNotifications()).map(item => item.title))).toContain("Notifikasi browser");
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    (await registration.getNotifications({ tag: "notification-preflight" })).forEach(item => item.close());
  });
  const background = await context.newPage();
  await background.goto("about:blank");
  await session.send("ServiceWorker.deliverPushMessage", { origin: baseURL, registrationId, data: JSON.stringify({ title: "Chat Telegram baru", body: "Pesan baru perlu dibalas.", url: "/admin/telegram-inbox?conversation=" + "a".repeat(32), tag: "telegram-test", kind: "telegram", _audit: { delivery_id: "b".repeat(32), ack_token: "c".repeat(43) } }) });
  await expect.poll(() => deviceAcks.map(ack => ack.stage)).toEqual(expect.arrayContaining(["push_received", "notification_show_resolved"]));
  expect(workerErrors).toEqual([]);
  // Linux's notification daemon can accept showNotification() without keeping
  // an entry in getNotifications(). The service-worker ACK above verifies the
  // real display API resolved; inspect the entry too when the host exposes it.
  const notification = await page.evaluate(async () => {
    const [item] = await (await navigator.serviceWorker.ready).getNotifications();
    return item ? { title: item.title, url: item.data.url } : null;
  });
  if (notification) {
    expect(notification.title).toBe("Chat Telegram baru");
    expect(notification.url).toBe(baseURL + "/admin/telegram-inbox?conversation=" + "a".repeat(32));
  }
  await session.send("ServiceWorker.deliverPushMessage", { origin: baseURL, registrationId, data: JSON.stringify({ title: "Chat Telegram baru", body: "Pesan susulan perlu dibalas.", url: "/admin/telegram-inbox?conversation=" + "a".repeat(32), tag: "telegram-test", kind: "telegram", _audit: { delivery_id: "d".repeat(32), ack_token: "e".repeat(43) } }) });
  await expect.poll(() => deviceAcks.filter(ack => ack.stage === "notification_show_resolved").length).toBe(2);
  await background.close();
});
