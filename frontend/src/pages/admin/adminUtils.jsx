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
