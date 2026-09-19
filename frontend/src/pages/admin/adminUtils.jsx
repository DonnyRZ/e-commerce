export const fmtMoney = (amount, currency = "UZS") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount ?? 0);

export const fmtDate = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })
    : "—";

export const inputClass =
  "h-10 w-full border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-[#145A46]";

const TONES = {
  emerald: "bg-[#145A46]/10 text-[#145A46]",
  blue: "bg-sky-100 text-sky-800",
  amber: "bg-amber-100 text-amber-800",
  red: "bg-red-100 text-red-700",
  neutral: "bg-neutral-100 text-neutral-600",
};

export const statusTone = (s) =>
  ({
    paid: "emerald",
    delivered: "emerald",
    active: "emerald",
    published: "emerald",
    in_stock: "emerald",
    processing: "blue",
    shipped: "blue",
    draft: "neutral",
    pending_payment: "amber",
    payment_review: "amber",
    supplier_shipping: "blue",
    received_by_admin: "blue",
    customer_shipping: "blue",
    review: "amber",
    pending_review: "amber",
    rejected: "red",
    low_stock: "amber",
    reconciliation_required: "amber",
    cancelled: "red",
    refunded: "red",
    failed: "red",
    expired: "red",
    out_of_stock: "red",
    inactive: "red",
    archived: "neutral",
  }[s] || "neutral");

export function StatusPill({ value, tone }) {
  return (
    <span
      data-testid={`pill-${value}`}
      className={`inline-flex items-center whitespace-nowrap px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${TONES[tone || statusTone(value)]}`}
    >
      {String(value || "—").replaceAll("_", " ")}
    </span>
  );
}

export function adminDeleteError(error, subject = "Item") {
  const detail = error?.response?.data?.detail;
  const code = typeof detail === "string" ? detail : detail?.error;
  const references = typeof detail === "object" ? detail?.references || {} : {};
  const labels = {
    order_items: "riwayat order",
    cart_items: "keranjang",
    wishlist_items: "wishlist",
    reservations: "reservasi stok",
  };
  const usedBy = Object.entries(references)
    .filter(([, count]) => Number(count) > 0)
    .map(([key, count]) => `${labels[key] || key} (${count})`)
    .join(", ");

  if (code === "product_must_be_inactive") {
    return "Nonaktifkan produk terlebih dahulu sebelum menghapus permanen.";
  }
  if (code === "last_variant") {
    return "Variant terakhir tidak dapat dihapus. Hapus produknya jika memang sudah tidak diperlukan.";
  }
  if (code === "product_in_use" || code === "variant_in_use") {
    return usedBy
      ? `${subject} masih digunakan oleh ${usedBy}. Lepaskan referensi tersebut terlebih dahulu.`
      : `${subject} masih digunakan dan belum dapat dihapus.`;
  }
  return `${subject} gagal dihapus. Coba lagi.`;
}
