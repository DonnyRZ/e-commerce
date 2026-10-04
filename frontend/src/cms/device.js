import { registerAdminPushDevice, removeAdminPushDevice } from "@/lib/api";

let registrationPromise;
export const pushSupported = () => Boolean(window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window);
export const isInstalled = () => window.matchMedia("(display-mode: standalone)").matches || window.matchMedia("(display-mode: fullscreen)").matches || navigator.standalone === true;

const AUTO_ENROLL_DISABLED_KEY = "cms-push-auto-enroll-disabled";

export function isPushAutoEnrollDisabled() {
  try { return window.localStorage.getItem(AUTO_ENROLL_DISABLED_KEY) === "1"; }
  catch { return false; }
}

export function setPushAutoEnrollDisabled(disabled) {
  try {
    if (disabled) window.localStorage.setItem(AUTO_ENROLL_DISABLED_KEY, "1");
    else window.localStorage.removeItem(AUTO_ENROLL_DISABLED_KEY);
  } catch { /* Push enrollment can still be controlled from the settings button. */ }
}

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

export async function registerDeviceSubscription(registration, subscription, publicKey) {
  let current = subscription;
  let result = await registerAdminPushDevice(current.toJSON());
  if (result?.replace) {
    // The provider previously returned 404/410 for this endpoint. Unsubscribe
    // locally and get a fresh endpoint instead of re-enabling a dead one.
    await current.unsubscribe();
    current = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: decodePublicKey(publicKey),
    });
    result = await registerAdminPushDevice(current.toJSON());
  }
  if (!result?.enabled || result?.replace) throw new Error("push_subscription_not_registered");
  return current;
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
