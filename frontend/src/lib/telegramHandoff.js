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

export const handoffText = {
  id: {
    waiting: "Pesan siap. Buka Telegram lalu tekan Kirim. Jika pesan tidak muncul, salin teks di bawah.",
    open: "Buka ulang Telegram", copy: "Salin pesan", copied: "Pesan disalin",
    sent: "Permintaan sudah diterima di Telegram. Admin akan melanjutkan pesananmu.",
    unknown: "Pengiriman belum dapat dipastikan. Periksa chat dahulu. Jika belum ada balasan, kirim ulang pesan ini; balasan mungkin muncul dua kali.",
    retained: "Jika Telegram dibatalkan, keranjang tetap utuh. Produk permintaan dihapus setelah pesan berhasil dikirim.",
    new: "Buat permintaan baru", expired: "Permintaan kedaluwarsa. Buat permintaan baru.",
  },
  en: {
    waiting: "Your message is ready. Open Telegram and press Send. If the draft is missing, copy the text below.",
    open: "Reopen Telegram", copy: "Copy message", copied: "Message copied",
    sent: "Your request reached Telegram. An admin will continue your order.",
    unknown: "Delivery is uncertain. Check the chat first. If no reply arrived, resend this message; a duplicate reply is possible.",
    retained: "Your cart stays intact if you cancel Telegram; submitted items are removed only after the message is sent.",
    new: "Create a new request", expired: "This request expired. Create a new request.",
  },
  uz: {
    waiting: "Xabar tayyor. Telegramni ochib, Yuborish tugmasini bosing. Matn chiqmasa, quyidagi matnni nusxalang.",
    open: "Telegramni qayta ochish", copy: "Xabarni nusxalash", copied: "Xabar nusxalandi",
    sent: "So‘rovingiz Telegramga yetib bordi. Admin buyurtmangizni davom ettiradi.",
    unknown: "Yetkazilganligi noma’lum. Avval chatni tekshiring. Javob bo‘lmasa, xabarni qayta yuboring; javob takrorlanishi mumkin.",
    retained: "Telegram bekor qilinsa, savat o‘zgarishsiz qoladi; so‘rov mahsulotlari xabar yuborilgandan keyingina o‘chiriladi.",
    new: "Yangi so‘rov yaratish", expired: "So‘rov muddati tugagan. Yangi so‘rov yarating.",
  },
  ru: {
    waiting: "Сообщение готово. Откройте Telegram и нажмите Отправить. Если текста нет, скопируйте его ниже.",
    open: "Открыть Telegram снова", copy: "Копировать сообщение", copied: "Сообщение скопировано",
    sent: "Запрос получен в Telegram. Администратор продолжит оформление заказа.",
    unknown: "Результат отправки неизвестен. Сначала проверьте чат. Если ответа нет, отправьте сообщение повторно; возможен повторный ответ.",
    retained: "Если отменить переход в Telegram, корзина останется без изменений; товары запроса удалятся только после отправки сообщения.",
    new: "Создать новый запрос", expired: "Срок запроса истёк. Создайте новый запрос.",
  },
};
