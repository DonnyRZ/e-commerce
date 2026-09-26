import { act } from "react";
import { createRoot } from "react-dom/client";
import CartPage from "./CartPage";
import { createTelegramCartInquiry } from "@/lib/api";

jest.mock("@tanstack/react-query", () => ({ useQuery: (options) => options.queryKey[0] === "telegram-inquiry-status"
  ? { isSuccess: true, data: { available: true, store_username: "store" } } : { data: { status: "pending" } } }));
jest.mock("react-router-dom", () => ({ Link: ({ children }) => <span>{children}</span> }), { virtual: true });
jest.mock("@/i18n", () => ({ useI18n: () => ({ locale: "id", t: (key) => key }) }));
jest.mock("@/lib/AuthContext", () => ({ useAuth: () => ({}) }));
jest.mock("@/lib/ShopContext", () => ({ useShop: () => ({
  cart: { id: "cart", item_count: 1, subtotal: 100, items: [{ id: "a", quantity: 1, unit_price: 100, translations: {}, option_values: {} }] },
  cartMutationsBlocked: false, guestCartMode: true,
}) }));
jest.mock("@/lib/api", () => ({ createTelegramCartInquiry: jest.fn(), getTelegramInquiryStatus: jest.fn(), getTelegramCartInquiry: jest.fn() }));
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("@/components/common/PriceDisplay", () => () => <span>100</span>);
jest.mock("@/components/common/ImageWithFallback", () => () => <span>image</span>);

let root;
let container;
const originalLocation = window.location;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  Object.defineProperty(window, "crypto", { configurable: true, value: { randomUUID: () => "test-idempotency-key-123" } });
  createTelegramCartInquiry.mockReset();
  createTelegramCartInquiry.mockResolvedValue({ reference: "SC-test", telegram_url: "https://t.me/store?text=hello", message: "hello" });
  delete window.location;
  window.location = { assign: jest.fn() };
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  window.location = originalLocation;
});
const button = () => container.querySelector('[data-testid="cart-telegram-confirm"]');
test("cancelled navigation unlocks confirmation and exposes copyable message; retry reuses inquiry", async () => {
  await act(async () => root.render(<CartPage />));
  await act(async () => button().click());
  expect(button().disabled).toBe(false);
  expect(container.querySelector("textarea").value).toBe("hello");
  await act(async () => button().click());
  expect(createTelegramCartInquiry).toHaveBeenCalledTimes(1);
  expect(window.location.assign).toHaveBeenCalledTimes(2);
});
test("lost API response retries the same idempotency key", async () => {
  createTelegramCartInquiry.mockRejectedValueOnce(new Error("timeout"));
  await act(async () => root.render(<CartPage />));
  await act(async () => button().click());
  expect(button().disabled).toBe(false);
  await act(async () => button().click());
  expect(createTelegramCartInquiry.mock.calls[0][0].idempotencyKey).toBe(createTelegramCartInquiry.mock.calls[1][0].idempotencyKey);
});
