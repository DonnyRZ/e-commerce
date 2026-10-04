const { test, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function worker(clients = []) {
  const handlers = {}, notifications = [], opened = [];
  const cache = { add: async () => {} };
  const scope = {
    URL, fetch: async () => { throw new Error("offline"); },
    caches: { open: async () => cache, keys: async () => [], match: async () => "offline page", delete: async () => true },
    self: {
      location: { origin: "https://cms.example.com" },
      addEventListener: (name, handler) => { handlers[name] = handler; },
      registration: { showNotification: async (title, options) => notifications.push({ title, ...options }) },
      clients: { claim: async () => {}, matchAll: async () => clients, openWindow: async url => opened.push(url) },
      skipWaiting: async () => {},
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../public/cms-sw.js"), "utf8"), scope);
  async function emit(name, values) {
    let completion;
    handlers[name]({ ...values, waitUntil: promise => { completion = promise; } });
    await completion;
  }
  return { handlers, notifications, opened, emit };
}

test("notification click navigates and focuses an existing CMS app", async () => {
  const navigated = [];
  let focused = false, closed = false;
  const client = { url: "https://cms.example.com/admin/", navigate: async url => { navigated.push(url); return { focus: async () => { focused = true; } }; } };
  const instance = worker([client]);
  await instance.emit("notificationclick", { notification: { close: () => { closed = true; }, data: { url: "/admin/telegram-inbox?conversation=123" } } });
  expect(navigated).toEqual(["https://cms.example.com/admin/telegram-inbox?conversation=123"]);
  expect(focused && closed).toBeTruthy();
  expect(instance.opened).toEqual([]);
});

test("closed app opens safely and foreign/out-of-scope notification URLs return to inbox", async () => {
  for (const url of ["https://attacker.example/admin/", "/checkout", "javascript:alert(1)", "/admin/../account"]) {
    const instance = worker();
    await instance.emit("notificationclick", { notification: { close() {}, data: { url } } });
    expect(instance.opened).toEqual(["https://cms.example.com/admin/telegram-inbox"]);
  }
  const instance = worker();
  await instance.emit("notificationclick", { notification: { close() {}, data: { url: "/admin/orders/MOBILE-1" } } });
  expect(instance.opened).toEqual(["https://cms.example.com/admin/orders/MOBILE-1"]);
});

test("a window that closes during notification click opens a replacement CMS app", async () => {
  const instance = worker([{ url: "https://cms.example.com/admin/", navigate: async () => { throw new Error("window closed"); } }]);
  await instance.emit("notificationclick", { notification: { close() {}, data: { url: "/admin/orders/MOBILE-1" } } });
  expect(instance.opened).toEqual(["https://cms.example.com/admin/orders/MOBILE-1"]);
});

test("malformed push still shows a generic notification and only CMS windows are refreshed", async () => {
  const messages = [], storeMessages = [];
  const instance = worker([
    { url: "https://cms.example.com/admin/settings", postMessage: value => messages.push(value) },
    { url: "https://cms.example.com/", postMessage: value => storeMessages.push(value) },
  ]);
  await instance.emit("push", { data: { json() { throw new Error("invalid payload"); } } });
  expect(instance.notifications[0].title).toBe("CMS memerlukan perhatian");
  expect(messages).toEqual([{ type: "CMS_PUSH", kind: "telegram" }]);
  expect(storeMessages).toEqual([]);
});

test("repeated Telegram messages re-alert while keeping the conversation notification tag", async () => {
  const instance = worker();
  const payload = {
    title: "Chat Telegram baru",
    url: "/admin/telegram-inbox?conversation=123",
    tag: "cms-telegram:/admin/telegram-inbox?conversation=123",
    kind: "telegram",
  };

  await instance.emit("push", { data: { json: () => ({ ...payload, body: "Pesan pertama" }) } });
  await instance.emit("push", { data: { json: () => ({ ...payload, body: "Pesan susulan" }) } });

  expect(instance.notifications).toHaveLength(2);
  expect(instance.notifications.map(({ tag, renotify }) => ({ tag, renotify }))).toEqual([
    { tag: payload.tag, renotify: true },
    { tag: payload.tag, renotify: true },
  ]);
});

test("API, media and store requests are never cached; only CMS navigation has an offline fallback", async () => {
  const instance = worker();
  for (const url of ["/api/v1/admin/orders", "/api/v1/cms/media/file/test", "/account"]) {
    let intercepted = false;
    instance.handlers.fetch({ request: { mode: "cors", url: "https://cms.example.com" + url }, respondWith: () => { intercepted = true; } });
    expect(intercepted).toBeFalsy();
  }
  let response;
  instance.handlers.fetch({ request: { mode: "navigate", url: "https://cms.example.com/admin/orders" }, respondWith: promise => { response = promise; } });
  expect(await response).toBe("offline page");
});
