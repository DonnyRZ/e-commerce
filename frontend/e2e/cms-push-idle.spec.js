const { test, expect } = require("@playwright/test");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

// Isolated native browser test: no FCM/Telegram traffic or production DB.
test("closed CMS and stopped worker display push without notification image networking", async ({ browser }) => {
  const worker = fs.readFileSync(path.join(__dirname, "../public/cms-sw.js"), "utf8");
  for (const legacy of [true, false]) {
    const acks = [], images = [], sockets = new Set();
    let releaseImages;
    const imageGate = new Promise(resolve => { releaseImages = resolve; });
    const source = legacy ? worker.replace("icon: NOTIFICATION_ICON, badge: NOTIFICATION_BADGE,", 'icon: "/admin/pwa/icon-192.png", badge: "/admin/pwa/badge-96.png",') : worker;
    const server = http.createServer(async (request, response) => {
      if (request.url === "/admin/cms-sw.js") {
        response.setHeader("Content-Type", "application/javascript");
        response.setHeader("Cache-Control", "no-store");
        response.end(source);
      } else if (request.url.startsWith("/admin/pwa/")) {
        images.push(request.url);
        await imageGate;
        response.setHeader("Content-Type", "image/png");
        response.end(fs.readFileSync(path.join(__dirname, "../public/pwa/", path.basename(request.url))));
      } else if (request.url === "/api/v1/admin/push/delivery-ack") {
        let body = "";
        for await (const chunk of request) body += chunk;
        acks.push(JSON.parse(body));
        response.writeHead(204).end();
      } else {
        response.setHeader("Content-Type", "text/html");
        response.end("<!doctype html><title>CMS push isolation</title>");
      }
    });
    server.on("connection", socket => { sockets.add(socket); socket.on("close", () => sockets.delete(socket)); });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    const origin = "http://127.0.0.1:" + server.address().port;
    const context = await browser.newContext({ permissions: ["notifications"] });
    try {
      const observer = await context.newPage();
      const session = await context.newCDPSession(observer);
      let registrationId;
      session.on("ServiceWorker.workerRegistrationUpdated", ({ registrations }) => {
        const registration = registrations.find(item => item.scopeURL === origin + "/admin/");
        if (registration) registrationId = registration.registrationId;
      });
      await session.send("ServiceWorker.enable");
      const cms = await context.newPage();
      await cms.goto(origin + "/admin/");
      await cms.evaluate(async () => {
        await navigator.serviceWorker.register("/admin/cms-sw.js", { scope: "/admin/" });
        await navigator.serviceWorker.ready;
      });
      await expect.poll(() => registrationId).toBeTruthy();
      await cms.close();
      await session.send("ServiceWorker.stopAllWorkers");
      const start = Date.now();
      await session.send("ServiceWorker.deliverPushMessage", {
        origin, registrationId,
        data: JSON.stringify({
          title: "Chat Telegram baru", body: "Pesan baru perlu dibalas.",
          url: "/admin/telegram-inbox?conversation=" + "a".repeat(32),
          tag: "cms-telegram:event-one", kind: "telegram",
          _audit: { delivery_id: "b".repeat(32), ack_token: "c".repeat(43) },
        }),
      });
      await expect.poll(() => acks.some(ack => ack.stage === "push_received")).toBeTruthy();
      if (legacy) {
        await expect.poll(() => images.length).toBe(2);
        await observer.waitForTimeout(500);
        expect(acks.some(ack => ack.stage === "notification_show_resolved")).toBeFalsy();
        releaseImages();
      }
      await expect.poll(() => acks.some(ack => ack.stage === "notification_show_resolved"), { timeout: 3000 }).toBeTruthy();
      const display = acks.find(ack => ack.stage === "notification_show_resolved");
      expect(display.worker_version).toBe("inline-icons-v2");
      expect(Date.parse(display.client_started_at)).toBeGreaterThan(0);
      expect(display.event_elapsed_ms).toBeGreaterThanOrEqual(0);
      if (!legacy) {
        expect(images).toEqual([]);
        expect(Date.now() - start).toBeLessThan(3000);
        expect(display.event_elapsed_ms).toBeLessThan(1000);
      }
      console.log(JSON.stringify({ legacy_network_icons: legacy, elapsed_ms: Date.now() - start, display_ms: display.event_elapsed_ms, image_requests: images.length }));
    } finally {
      releaseImages();
      await context.close();
      for (const socket of sockets) socket.destroy();
      await new Promise(resolve => server.close(resolve));
    }
  }
});
