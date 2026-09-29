import { Check } from "lucide-react";

export const ORDER_STEPS = [
  ["inquiry", "Pending Order"],
  ["payment", "Pembayaran"],
  ["supplier_shipping", "Supplier mengirim"],
  ["received_by_admin", "Diterima admin"],
  ["customer_shipping", "Dikirim ke customer"],
  ["delivered", "Selesai"],
];

export function normalizeOrderStage(stage) {
  if (["pending_payment", "payment_review"].includes(stage)) return "payment";
  if (["paid", "processing"].includes(stage)) return "supplier_shipping";
  if (stage === "shipped") return "customer_shipping";
  return stage;
}

export function workflowStageForStatus(status) {
  const statusStages = {
    pending_payment: "payment",
    payment_review: "payment",
    paid: "supplier_shipping",
    processing: "supplier_shipping",
    supplier_shipping: "received_by_admin",
    received_by_admin: "customer_shipping",
    customer_shipping: "customer_shipping",
    shipped: "customer_shipping",
    delivered: "delivered",
  };
  return statusStages[status] || normalizeOrderStage(status);
}

export function OrderProgress({
  currentStage,
  variant = "full",
  className = "",
  testId,
}) {
  const current = normalizeOrderStage(currentStage);
  const currentIndex = ORDER_STEPS.findIndex(([key]) => key === current);
  const isCompact = variant === "compact";

  return (
    <nav
      aria-label={isCompact ? "Order progress" : "Tahapan order"}
      className={className}
      data-testid={testId}
    >
      <ol
        className={isCompact
          ? "flex items-center gap-1 overflow-hidden"
          : "grid grid-cols-3 gap-x-2 gap-y-4 sm:grid-cols-6"}
      >
        {ORDER_STEPS.map(([key, label], index) => {
          const complete = currentIndex >= 0 && index < currentIndex;
          const active = index === currentIndex;
          return (
            <li
              key={key}
              aria-current={active ? "step" : undefined}
              className={isCompact
                ? "flex min-w-0 flex-1 items-center gap-1"
                : "relative flex min-w-0 flex-col items-center text-center text-xs"}
              data-stage={key}
            >
              {isCompact ? (
                <>
                  <span
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${complete || active ? "border-[#02422C] bg-[#02422C] text-white" : "border-neutral-300 bg-white text-neutral-300"}`}
                    title={label}
                  >
                    {complete ? <Check className="h-3 w-3" aria-hidden="true" /> : active ? <span className="h-2 w-2 rounded-full bg-current" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                  </span>
                  <span className={`hidden truncate text-[11px] sm:block ${active ? "font-semibold text-[#02422C]" : complete ? "text-neutral-600" : "text-neutral-400"}`}>
                    {label}
                  </span>
                  {index < ORDER_STEPS.length - 1 ? (
                    <span className={`h-px min-w-2 flex-1 ${complete ? "bg-[#02422C]" : "bg-neutral-200"}`} />
                  ) : null}
                </>
              ) : (
                <>
                  <div className="relative flex w-full justify-center">
                    {index < ORDER_STEPS.length - 1 ? (
                      <span
                        aria-hidden="true"
                        className={`absolute left-1/2 right-[-50%] top-4 h-px ${index === 2 ? "hidden sm:block" : ""} ${complete ? "bg-[#02422C]" : "bg-[#CD9B3A]/50"}`}
                      />
                    ) : null}
                    <span className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border font-medium ${complete || active ? "border-[#02422C] bg-[#02422C] text-white" : "border-neutral-200 bg-white text-neutral-400"}`}>
                      {complete ? <Check className="h-4 w-4" aria-hidden="true" /> : index + 1}
                    </span>
                  </div>
                  <span className={`mt-2 block min-h-8 max-w-full px-1 leading-tight ${active ? "font-semibold text-[#02422C]" : complete ? "text-neutral-600" : "text-neutral-500"}`}>
                    {label}
                  </span>
                </>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
