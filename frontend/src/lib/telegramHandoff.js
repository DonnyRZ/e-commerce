export function cartSignature(cart, locale) {
  return JSON.stringify([cart?.id, locale, (cart?.items || []).map(
    (item) => [item.id, item.variant_id, item.quantity, item.unit_price]
  ).sort((a, b) => String(a[0]).localeCompare(String(b[0])))]);
}

const STORAGE = "mc.telegram.handoff.v1";
export function readHandoff(signature) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE));
    return saved?.signature === signature && saved.until > Date.now() ? saved : null;
  } catch { return null; }
}
export function saveHandoff(value) {
  try { sessionStorage.setItem(STORAGE, JSON.stringify(value)); } catch { /* private mode */ }
}

export function telegramInquiryMessage(inquiry) {
  if (typeof inquiry?.message === "string" && inquiry.message.trim()) {
    return inquiry.message;
  }
  try {
    return new URL(inquiry?.telegram_url || "").searchParams.get("text") || "";
  } catch {
    return "";
  }
}

export function telegramChatUrl(username, message) {
  const normalizedUsername = String(username || "").trim().replace(/^@/, "");
  const preparedText = String(message || "").trim();
  if (!/^[a-zA-Z0-9_]{5,32}$/.test(normalizedUsername) || !preparedText) return null;

  const url = new URL(`https://t.me/${normalizedUsername}`);
  url.searchParams.set("text", preparedText);
  return url.toString();
}

export const handoffText = {
  id: {
    waiting: "Chat toko sudah dibuka di Telegram. Tekan Kirim di sana untuk mengirim permintaan.",
    sent: "Permintaan sudah diterima di Telegram. Admin akan melanjutkan pesananmu.",
    unknown: "Pengiriman belum dapat dipastikan. Periksa chat dahulu. Jika belum ada balasan, kirim ulang pesan ini; balasan mungkin muncul dua kali.",
    retained: "Jika Telegram dibatalkan, keranjang tetap utuh. Produk permintaan dihapus setelah pesan berhasil dikirim.",
    new: "Buat permintaan baru", expired: "Permintaan kedaluwarsa. Buat permintaan baru.",
  },
  en: {
    waiting: "The store chat opened in Telegram. Tap Send there to submit the inquiry.",
    sent: "Your request reached Telegram. An admin will continue your order.",
    unknown: "Delivery is uncertain. Check the chat first. If no reply arrived, resend this message; a duplicate reply is possible.",
    retained: "Your cart stays intact if you cancel Telegram; submitted items are removed only after the message is sent.",
    new: "Create a new request", expired: "This request expired. Create a new request.",
  },
  uz: {
    waiting: "Telegramda do‘kon chati ochildi. So‘rovni yuborish uchun u yerda Yuborish tugmasini bosing.",
    sent: "So‘rovingiz Telegramga yetib bordi. Admin buyurtmangizni davom ettiradi.",
    unknown: "Yetkazilganligi noma’lum. Avval chatni tekshiring. Javob bo‘lmasa, xabarni qayta yuboring; javob takrorlanishi mumkin.",
    retained: "Telegram bekor qilinsa, savat o‘zgarishsiz qoladi; so‘rov mahsulotlari xabar yuborilgandan keyingina o‘chiriladi.",
    new: "Yangi so‘rov yaratish", expired: "So‘rov muddati tugagan. Yangi so‘rov yarating.",
  },
  ru: {
    waiting: "Чат магазина открыт в Telegram. Нажмите там «Отправить», чтобы передать запрос.",
    sent: "Запрос получен в Telegram. Администратор продолжит оформление заказа.",
    unknown: "Результат отправки неизвестен. Сначала проверьте чат. Если ответа нет, отправьте сообщение повторно; возможен повторный ответ.",
    retained: "Если отменить переход в Telegram, корзина останется без изменений; товары запроса удалятся только после отправки сообщения.",
    new: "Создать новый запрос", expired: "Срок запроса истёк. Создайте новый запрос.",
  },
};
