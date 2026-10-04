/* The CMS never caches authenticated pages, API responses, or customer media. */
const OFFLINE_CACHE = "cantik-cms-offline-v1";
const OFFLINE_URL = "/admin/offline.html";
self.addEventListener("install", event => {
  event.waitUntil(caches.open(OFFLINE_CACHE).then(cache => cache.add(OFFLINE_URL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("cantik-cms-offline-") && key !== OFFLINE_CACHE).map(key => caches.delete(key)))),
    self.clients.claim(),
  ]));
});
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.mode === "navigate" && url.origin === self.location.origin && url.pathname.startsWith("/admin/")) {
    event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
  }
});
function notificationUrl(value) {
  try {
    const url = new URL(value || "/admin/telegram-inbox", self.location.origin);
    if (url.origin === self.location.origin && url.pathname.startsWith("/admin/")) return url.href;
  } catch { /* Unsafe links return to the inbox. */ }
  return new URL("/admin/telegram-inbox", self.location.origin).href;
}
function reportPushStage(audit, stage) {
  if (!audit?.delivery_id || !audit?.ack_token) return Promise.resolve();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3000);
  return fetch("/api/v1/admin/push/delivery-ack", {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({delivery_id: audit.delivery_id, ack_token: audit.ack_token, stage}),
    signal: controller.signal,
  }).catch(() => {}).finally(() => clearTimeout(timeout));
}
self.addEventListener("push", event => {
  let data = {};
  try { data = event.data?.json() || {}; } catch { /* Display a useful generic notification. */ }
  const url = notificationUrl(data.url);
  const audit = data._audit || {};
  const receivedAck = reportPushStage(audit, "push_received");
  event.waitUntil(Promise.all([
    (async () => {
      try {
        await self.registration.showNotification(String(data.title || "CMS memerlukan perhatian").slice(0, 200), {
          body: String(data.body || "Buka CMS untuk melihat pesan dan order terbaru.").slice(0, 500),
          icon: "/admin/pwa/icon-192.png", badge: "/admin/pwa/badge-96.png",
          tag: String(data.tag || "cantik-cms"), renotify: true, data: {url},
        });
        await reportPushStage(audit, "notification_show_resolved");
      } catch (error) {
        await reportPushStage(audit, "notification_show_failed");
        throw error;
      }
    })(),
    receivedAck,
    self.clients.matchAll({type: "window", includeUncontrolled: true}).then(clients => {
      clients.filter(client => new URL(client.url).pathname.startsWith("/admin/")).forEach(client => client.postMessage({type: "CMS_PUSH", kind: data.kind || "telegram"}));
    }),
  ]));
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const url = notificationUrl(event.notification.data?.url);
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    const existing = clients.find(client => new URL(client.url).pathname.startsWith("/admin/"));
    if (existing) {
      try {
        const navigated = await existing.navigate(url);
        if (navigated) return await navigated.focus();
      } catch { /* The window may close while the notification is being opened. */ }
    }
    return self.clients.openWindow(url);
  })());
});
