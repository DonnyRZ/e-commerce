import {
  cartSignature,
  handoffText,
  readHandoff,
  saveHandoff,
  telegramChatUrl,
  telegramInquiryMessage,
} from "./telegramHandoff";

beforeEach(() => sessionStorage.clear());
test("same cart snapshot keeps its key across remounts; changes invalidate it", () => {
  const cart = { id: "cart", items: [{ id: "a", quantity: 1, unit_price: 100 }] };
  const signature = cartSignature(cart, "id");
  saveHandoff({ signature, key: "retry-key", until: Date.now() + 10000 });
  expect(readHandoff(signature).key).toBe("retry-key");
  expect(readHandoff(cartSignature({ ...cart, id: "other" }, "id"))).toBeNull();
  expect(readHandoff(cartSignature({ ...cart, items: [{ id: "a", quantity: 2, unit_price: 100 }] }, "id"))).toBeNull();
  expect(readHandoff(cartSignature(cart, "en"))).toBeNull();
});
test("expired and corrupt sessions cannot resume", () => {
  saveHandoff({ signature: "x", until: 0 });
  expect(readHandoff("x")).toBeNull();
  sessionStorage.setItem("mc.telegram.handoff.v1", "broken");
  expect(readHandoff("x")).toBeNull();
});
test("all supported languages have recovery copy", () => {
  for (const language of ["id", "en", "uz", "ru"]) {
    expect(Object.keys(handoffText[language]).sort()).toEqual(Object.keys(handoffText.en).sort());
  }
});

test("Telegram links open the configured store chat directly with the prepared draft", () => {
  const message = "Salom & test\nSC-0123456789ABCDEF0123456789ABCDEF";
  const chatUrl = telegramChatUrl("@CantikByIndonesia", message);
  const appUrl = new URL(chatUrl);

  expect(appUrl.origin).toBe("https://t.me");
  expect(appUrl.pathname).toBe("/CantikByIndonesia");
  expect(appUrl.searchParams.get("url")).toBeNull();
  expect(appUrl.searchParams.get("domain")).toBeNull();
  expect(appUrl.searchParams.get("text")).toBe(message);
  expect(telegramChatUrl("bad username", message)).toBeNull();
  expect(telegramChatUrl("store", " ")).toBeNull();
});

test("inquiry message prefers the API text and falls back to its direct link draft", () => {
  expect(telegramInquiryMessage({
    message: "prepared message",
    telegram_url: "https://t.me/store?text=link+message",
  })).toBe("prepared message");
  expect(telegramInquiryMessage({
    telegram_url: "https://t.me/store?text=link+message",
  })).toBe("link message");
});
