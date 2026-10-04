import { removeAdminPushDevice } from "@/lib/api";

let registrationPromise;
export const pushSupported = () => Boolean(window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window);
export const isInstalled = () => window.matchMedia("(display-mode: standalone)").matches || window.matchMedia("(display-mode: fullscreen)").matches || navigator.standalone === true;

export function decodePublicKey(value) {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(base64 + "=".repeat((4 - base64.length % 4) % 4)), c => c.charCodeAt(0));
}

export function matchesPublicKey(subscription, value) {
  const previous = subscription?.options?.applicationServerKey;
  if (!previous) return true;
  const actual = new Uint8Array(previous);
  const expected = decodePublicKey(value);
  return actual.length === expected.length && actual.every((byte, index) => byte === expected[index]);
}

export async function cmsServiceWorker() {
  if (!window.isSecureContext || !("serviceWorker" in navigator)) throw new Error("service_worker_unavailable");
  registrationPromise ||= navigator.serviceWorker.register("/admin/cms-sw.js", { scope: "/admin/", updateViaCache: "none" }).catch(error => {
    registrationPromise = null;
    throw error;
  });
  const registration = await registrationPromise;
  if (registration.active) return registration;
  let timer;
  try {
    await Promise.race([
      navigator.serviceWorker.ready,
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("service_worker_timeout")), 15000); }),
    ]);
    return registration;
  } finally {
    clearTimeout(timer);
  }
}

export async function stopDeviceNotifications() {
  if (!("serviceWorker" in navigator)) return;
  const registration = await navigator.serviceWorker.getRegistration("/admin/");
  const subscription = await registration?.pushManager?.getSubscription();
  if (!subscription) return;
  try {
    await removeAdminPushDevice(subscription.endpoint);
  } finally {
    await subscription.unsubscribe();
    const notifications = await registration.getNotifications();
    notifications.forEach(notification => notification.close());
  }
}
