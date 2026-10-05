const { test, expect } = require("@playwright/test");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

for (const [failure, recovery] of [["http-503", "foreground"], ["timeout", "foreground"], ["http-503", "sync"]]) {
  test(`Telegram display does not wait for ${failure}; original receipts survive a stopped worker and recover via ${recovery}`, async ({ browser }) => {
    // Exercise browsers without Background Sync; foreground recovery must work too.
    const worker = 'Object.defineProperty(self.registration, "sync", {value: undefined});\n'
      + fs.readFileSync(path.join(__dirname, "../public/cms-sw.js"), "utf8");
    const sockets = new Set(), accepted = [], attempts = [];
    let unavailable = true;
    const server = http.createServer(async (request, response) => {
      if (request.url === "/admin/cms-sw.js") {
        response.setHeader("Content-Type", "application/javascript");
        response.setHeader("Cache-Control", "no-store");
        response.end(worker);
      } else if (request.url === "/api/v1/admin/push/delivery-ack") {
        let body = "";
        for await (const chunk of request) body += chunk;
        const receipt = JSON.parse(body);
        attempts.push(receipt);
        if (unavailable) {
          if (failure === "http-503") response.writeHead(503).end();
          return;
        }
        accepted.push(receipt);
        response.writeHead(204).end();
      } else {
        response.setHeader("Content-Type", "text/html");
        response.end("<!doctype html><title>CMS receipt recovery</title>");
      }
    });
    server.on("connection", socket => { sockets.add(socket); socket.on("close", () => sockets.delete(socket)); });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    const origin = "http://127.0.0.1:" + server.address().port;
    const context = await browser.newContext({ permissions: ["notifications"] });
    let observer;
    const readReceipts = async () => {
      return observer.evaluate(async () => {
        if (!(await indexedDB.databases()).some(db => db.name === "cantik-cms-push-acks-v1")) return [];
        return new Promise((resolve, reject) => {
        const request = indexedDB.open("cantik-cms-push-acks-v1", 1);
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const db = request.result;
          const transaction = db.transaction("receipts", "readonly");
          const query = transaction.objectStore("receipts").getAll();
          transaction.oncomplete = () => { db.close(); resolve(query.result); };
          transaction.onabort = () => { db.close(); reject(transaction.error); };
        };
        });
      });
    };
    try {
      observer = await context.newPage();
      // Inspect same-origin storage outside CMS scope, without keeping a CMS page open.
      await observer.goto(origin + "/receipt-inspector");
      const session = await context.newCDPSession(observer);
      let registrationId;
      session.on("ServiceWorker.workerRegistrationUpdated", ({ registrations }) => {
        const row = registrations.find(item => item.scopeURL === origin + "/admin/");
        if (row) registrationId = row.registrationId;
      });
      await session.send("ServiceWorker.enable");
      const cms = await context.newPage();
      await cms.goto(origin + "/admin/");
      await cms.evaluate(async () => {
        await navigator.serviceWorker.register("/admin/cms-sw.js", {scope: "/admin/"});
        await navigator.serviceWorker.ready;
      });
      await expect.poll(() => registrationId).toBeTruthy();
      await cms.close();
      await session.send("ServiceWorker.stopAllWorkers");
      await session.send("ServiceWorker.deliverPushMessage", {
        origin, registrationId,
        data: JSON.stringify({title: "Chat Telegram baru", kind: "telegram", tag: "cms-telegram:recovery", url: "/admin/telegram-inbox?conversation=" + "a".repeat(32), _audit: {delivery_id: "b".repeat(32), ack_token: "c".repeat(43)}}),
      });
      await expect.poll(async () => (await readReceipts()).length).toBe(2);
      const saved = await readReceipts();
      const display = saved.find(row => row.payload.stage === "notification_show_resolved").payload;
      expect(display.event_elapsed_ms).toBeLessThan(1000);
      expect(accepted).toEqual([]);
      expect(display.worker_version).toBe("durable-acks-v3");
      expect(saved.every(row => !row.payload.body && !row.payload.url && !row.payload.title)).toBeTruthy();
      await expect.poll(() => attempts.length).toBe(2);
      await session.send("ServiceWorker.stopAllWorkers");
      unavailable = false;
      if (recovery === "sync") {
        await session.send("ServiceWorker.dispatchSyncEvent", {origin, registrationId, tag: "cms-push-acks", lastChance: false});
      } else {
        const resumed = await context.newPage();
        await resumed.goto(origin + "/admin/");
        await resumed.evaluate(async () => {
          const registration = await navigator.serviceWorker.getRegistration("/admin/");
          registration.active.postMessage({type: "CMS_FLUSH_PUSH_ACKS"});
        });
      }
      await expect.poll(() => accepted.length).toBe(2);
      for (const row of saved) {
        expect(accepted.find(receipt => receipt.stage === row.payload.stage)).toEqual(row.payload);
      }
      await expect.poll(async () => (await readReceipts()).length).toBe(0);
      console.log(JSON.stringify({failure, recovery, display_ms: display.event_elapsed_ms, receipts_recovered: accepted.length, original_times_preserved: true}));
    } finally {
      await context.close();
      for (const socket of sockets) socket.destroy();
      await new Promise(resolve => server.close(resolve));
    }
  });
}
