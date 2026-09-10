import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getSellerOrders } from "@/lib/api";
import PriceDisplay, { LOCALE_TAGS } from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

export function FulfillmentBadge({ status, testId }) {
  const { t } = useI18n();
  const styles = {
    pending: "bg-neutral-200 text-neutral-700",
    processing: "bg-amber-100 text-amber-800",
    shipped: "bg-blue-100 text-blue-800",
    delivered: "bg-[#145A46] text-white",
    cancelled: "bg-red-100 text-red-700",
  };
  return (
    <span data-testid={testId} className={`inline-block px-2 py-0.5 text-[11px] font-semibold uppercase ${styles[status] || "bg-neutral-200 text-neutral-600"}`}>
      {t(`seller.fulfillment.${status}`)}
    </span>
  );
}

export function PaymentBadge({ state, testId }) {
  const { t } = useI18n();
  const paid = state === "paid";
  return (
    <span data-testid={testId} className={`inline-block px-2 py-0.5 text-[11px] font-semibold uppercase ${paid ? "bg-[#145A46] text-white" : "bg-neutral-200 text-neutral-600"}`}>
      {t(`orders.pay.${state}`)}
    </span>
  );
}

const selectClass = "h-10 border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-[#145A46]";

export default function SellerOrdersPage() {
  const { t, locale } = useI18n();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["seller-orders", { status, page }],
    queryFn: () => getSellerOrders({ status: status || undefined, page, page_size: 20 }),
  });
  const data = query.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const tag = LOCALE_TAGS[locale] || "en-US";

  return (
    <div data-testid="seller-orders-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{t("seller.orders.title")}</h1>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className={selectClass} data-testid="orders-filter-status" aria-label={t("seller.orders.fulfillment")}>
          <option value="">{t("seller.orders.allFulfillments")}</option>
          {["pending", "processing", "shipped", "delivered", "cancelled"].map((s) => (
            <option key={s} value={s}>{t(`seller.fulfillment.${s}`)}</option>
          ))}
        </select>
      </div>

      <div className="mt-5 overflow-x-auto border border-neutral-200 bg-white">
        {query.isLoading ? (
          <div className="p-5"><Skeleton className="h-40 w-full" /></div>
        ) : (data?.items || []).length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-neutral-400" data-testid="orders-empty">{t("seller.orders.empty")}</p>
        ) : (
          <table className="w-full min-w-[720px] text-sm" data-testid="orders-table">
            <thead>
              <tr className="border-b border-neutral-100 text-left text-xs text-neutral-400">
                <th className="px-5 py-2.5 font-medium">{t("seller.orders.order")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.orders.date")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.orders.recipient")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.orders.items")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.orders.payment")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.orders.fulfillment")}</th>
                <th className="px-4 py-2.5 text-right font-medium">{t("seller.orders.subtotal")}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((o) => (
                <tr key={o.order_number} className="border-b border-neutral-50 last:border-0 hover:bg-neutral-50" data-testid={`seller-order-row-${o.order_number}`}>
                  <td className="px-5 py-3">
                    <Link to={`/seller/orders/${o.order_number}`} className="font-semibold text-[#145A46] hover:underline" data-testid={`seller-order-${o.order_number}`}>
                      {o.order_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-xs text-neutral-500">
                    {new Intl.DateTimeFormat(tag, { dateStyle: "medium" }).format(new Date(o.created_at))}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {o.recipient}
                    <span className="block text-neutral-400">{o.destination}</span>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{o.item_count}</td>
                  <td className="px-4 py-3"><PaymentBadge state={o.payment_state} testId={`order-pay-${o.order_number}`} /></td>
                  <td className="px-4 py-3"><FulfillmentBadge status={o.fulfillment_status} testId={`order-ful-${o.order_number}`} /></td>
                  <td className="px-4 py-3 text-right"><PriceDisplay amount={o.seller_subtotal} className="text-xs" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 ? (
        <div className="mt-4 flex items-center gap-3 text-sm">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="orders-prev" className="h-9 border border-neutral-300 px-4 disabled:opacity-40">{t("seller.products.prev")}</button>
          <span className="text-xs text-neutral-500">{page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} data-testid="orders-next" className="h-9 border border-neutral-300 px-4 disabled:opacity-40">{t("seller.products.next")}</button>
        </div>
      ) : null}
    </div>
  );
}
