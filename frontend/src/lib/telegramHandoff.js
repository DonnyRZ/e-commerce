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

  const url = new URL("tg://resolve");
  url.searchParams.set("domain", normalizedUsername);
  url.searchParams.set("text", preparedText);
  return url.toString();
}

export const handoffText = {
  id: {
    waiting: "Template pesan tersedia di bawah. Salin dulu, lalu buka chat toko. Jika kolom pesan Telegram kosong, tempel template yang disalin lalu tekan Kirim.",
    open: "Buka chat toko di Telegram", copy: "Salin template pesan", copied: "Template pesan disalin", failed: "Tidak dapat menyalin otomatis. Tekan lama teks di atas untuk menyalinnya.",
    sent: "Permintaan sudah diterima di Telegram. Admin akan melanjutkan pesananmu.",
    unknown: "Pengiriman belum dapat dipastikan. Periksa chat dahulu. Jika belum ada balasan, kirim ulang pesan ini; balasan mungkin muncul dua kali.",
    retained: "Jika Telegram dibatalkan, keranjang tetap utuh. Produk permintaan dihapus setelah pesan berhasil dikirim.",
    new: "Buat permintaan baru", expired: "Permintaan kedaluwarsa. Buat permintaan baru.",
  },
  en: {
    waiting: "Your message template is below. Copy it first, then open the store chat. If Telegram's message field is empty, paste the copied template and press Send.",
    open: "Open store chat in Telegram", copy: "Copy message template", copied: "Message template copied", failed: "Could not copy automatically. Long-press the text above to copy it.",
    sent: "Your request reached Telegram. An admin will continue your order.",
    unknown: "Delivery is uncertain. Check the chat first. If no reply arrived, resend this message; a duplicate reply is possible.",
    retained: "Your cart stays intact if you cancel Telegram; submitted items are removed only after the message is sent.",
    new: "Create a new request", expired: "This request expired. Create a new request.",
  },
  uz: {
    waiting: "Xabar namunasi quyida. Avval nusxa oling, keyin do‘kon chatini oching. Telegramdagi xabar maydoni bo‘sh bo‘lsa, nusxalangan matnni joylashtirib, Yuborish tugmasini bosing.",
    open: "Telegramda do‘kon chatini ochish", copy: "Xabar namunasidan nusxa olish", copied: "Xabar nusxalandi", failed: "Avtomatik nusxa olib bo‘lmadi. Nusxa olish uchun yuqoridagi matnni bosib turing.",
    sent: "So‘rovingiz Telegramga yetib bordi. Admin buyurtmangizni davom ettiradi.",
    unknown: "Yetkazilganligi noma’lum. Avval chatni tekshiring. Javob bo‘lmasa, xabarni qayta yuboring; javob takrorlanishi mumkin.",
    retained: "Telegram bekor qilinsa, savat o‘zgarishsiz qoladi; so‘rov mahsulotlari xabar yuborilgandan keyingina o‘chiriladi.",
    new: "Yangi so‘rov yaratish", expired: "So‘rov muddati tugagan. Yangi so‘rov yarating.",
  },
  ru: {
    waiting: "Шаблон сообщения ниже. Сначала скопируйте его, затем откройте чат магазина. Если поле сообщения в Telegram пустое, вставьте скопированный текст и нажмите «Отправить».",
    open: "Открыть чат магазина в Telegram", copy: "Скопировать шаблон сообщения", copied: "Шаблон сообщения скопирован", failed: "Не удалось скопировать автоматически. Нажмите и удерживайте текст выше, чтобы скопировать его.",
    sent: "Запрос получен в Telegram. Администратор продолжит оформление заказа.",
    unknown: "Результат отправки неизвестен. Сначала проверьте чат. Если ответа нет, отправьте сообщение повторно; возможен повторный ответ.",
    retained: "Если отменить переход в Telegram, корзина останется без изменений; товары запроса удалятся только после отправки сообщения.",
    new: "Создать новый запрос", expired: "Срок запроса истёк. Создайте новый запрос.",
  },
};
