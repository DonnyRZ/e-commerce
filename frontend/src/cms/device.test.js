import { removeAdminPushDevice } from "@/lib/api";
import { decodePublicKey, matchesPublicKey, stopDeviceNotifications } from "./device";

jest.mock("@/lib/api", () => ({ removeAdminPushDevice: jest.fn() }));

afterEach(() => jest.clearAllMocks());

test("VAPID key decoding and comparison detect rotation and truncated keys", () => {
  const expected = Uint8Array.from([4, 12, 255, 3]);
  const value = btoa(String.fromCharCode(...expected)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  expect(decodePublicKey(value)).toEqual(expected);
  expect(matchesPublicKey({ options: { applicationServerKey: expected.buffer } }, value)).toBe(true);
  expect(matchesPublicKey({ options: { applicationServerKey: Uint8Array.from([4, 12]).buffer } }, value)).toBe(false);
  expect(matchesPublicKey({ options: { applicationServerKey: Uint8Array.from([4, 12, 255, 2]).buffer } }, value)).toBe(false);
});

test("logout unsubscribes this device and closes notifications even when the API is unavailable", async () => {
  const subscription = { endpoint: "https://fcm.googleapis.com/fcm/send/current", unsubscribe: jest.fn().mockResolvedValue(true) };
  const close = jest.fn();
  const registration = { pushManager: { getSubscription: async () => subscription }, getNotifications: async () => [{ close }] };
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { getRegistration: async () => registration } });
  removeAdminPushDevice.mockRejectedValueOnce(new Error("offline"));
  await expect(stopDeviceNotifications()).rejects.toThrow("offline");
  expect(removeAdminPushDevice).toHaveBeenCalledWith(subscription.endpoint);
  expect(subscription.unsubscribe).toHaveBeenCalledTimes(1);
  expect(close).toHaveBeenCalledTimes(1);
});

test("logout without a subscription has no device side effects", async () => {
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { getRegistration: async () => undefined } });
  await stopDeviceNotifications();
  expect(removeAdminPushDevice).not.toHaveBeenCalled();
});
