import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { getSellerOrder, updateSellerFulfillment } from "@/lib/api";
import PriceDisplay, { LOCALE_TAGS } from "@/components/common/PriceDisplay";
import { FulfillmentBadge, PaymentBadge } from "@/pages/seller/SellerOrdersPage";
import { Skeleton } from "@/components/ui/skeleton";

const NEXT = { pending: "processing", processing: "shipped", shipped: "delivered" };
const inputClass = "h-10 border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-[#145A46]";

export default function SellerOrderDetailPage() {
  const { t, locale } = useI18n();
  const { orderNumber } = useParams();
  const queryClient = useQueryClient();
  const [carrier, setCarrier] = useState("");
  const [tracking, setTracking] = useState("");
  const [busy, setBusy] = useState(false);

  const orderQuery = useQuery({
    queryKey: ["seller-order", orderNumber],
    queryFn: () => getSellerOrder(orderNumber),
    retry: false,
  });

  const transition = async (status) => {
    if (busy) return;
    setBusy(true);
    try {
      const payload = { status };
      if (status === "shipped") {
        if (carrier) payload.shipping_carrier = carrier;
        if (tracking) payload.tracking_number = tracking;
      }
      await updateSellerFulfillment(orderNumber, payload);
      toast.success(t("seller.orderDetail.updated"));
      queryClient.invalidateQueries({ queryKey: ["seller-order", orderNumber] });
      queryClient.invalidateQueries({ queryKey: ["seller-orders"] });
    } catch (err) {
      const d = err?.response?.data?.detail;
      const code = typeof d === "string" ? d : d?.error;
      if (code === "invalid_transition") toast.error(t("seller.orderDetail.invalidTransition"));
      else if (code === "payment_not_eligible") toast.error(t("seller.orderDetail.blockedUnpaid"));
      else toast.error(t("seller.orderDetail.failed"));
    } finally {
      setBusy(false);
    }
  };

  if (orderQuery.isLoading) {
    return <div data-testid="seller-order-loading"><Skeleton className="h-8 w-56" /><Skeleton className="mt-6 h-72 w-full" /></div>;
  }
  if (orderQuery.isError) {
    return (
      <div className="py-16 text-center" data-testid="seller-order-notfound">
        <p className="text-sm text-neutral-500">{t("errors.notFound")}</p>
        <Link to="/seller/orders" className="mt-4 inline-flex h-10 items-center border border-neutral-300 px-6 text-sm">{t("orders.backToOrders")}</Link>
      </div>
    );
  }

  const order = orderQuery.data;
  const next = NEXT[order.fulfillment.status];
  const eligible = order.payment_state === "paid";
  const tag = LOCALE_TAGS[locale] || "en-US";
  const c = order.customer || {};

  return (
    <div data-testid="seller-order-detail">
      <Link to="/seller/orders" className="inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-900" data-testid="seller-order-back">
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        {t("orders.backToOrders")}
      </Link>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight" data-testid="seller-order-number">{order.order_number}</h1>
        <PaymentBadge state={order.payment_state} testId="seller-order-pay" />
        <FulfillmentBadge status={order.fulfillment.status} testId="seller-order-fulfillment" />
      </div>
      <p className="mt-1 text-xs text-neutral-400">
        {new Intl.DateTimeFormat(tag, { dateStyle: "medium", timeStyle: "short" }).format(new Date(order.created_at))}
        {" · "}{t("orders.orderStatus")}: {t(`orders.state.${order.order_status}`)}
      </p>

      <div className="mt-6 grid gap-5 xl:grid-cols-[1fr_340px]">
        <section className="border border-neutral-200 bg-white" data-testid="seller-order-items">
          <h2 className="border-b border-neutral-100 px-5 py-3 text-sm font-semibold">{t("seller.orderDetail.items")}</h2>
          <ul className="divide-y divide-neutral-100">
            {order.items.map((item) => (
              <li key={item.sku} className="flex gap-4 px-5 py-3" data-testid={`seller-order-item-${item.sku}`}>
                {item.image_url ? (
                  <img src={item.image_url} alt="" loading="lazy" className="aspect-[3/4] w-12 bg-neutral-100 object-cover" />
                ) : null}
                <div className="flex-1">
                  <p className="text-sm font-medium">{item.product_name}</p>
                  <p className="mt-0.5 text-xs text-neutral-500">
                    {Object.entries(item.option_values || {}).map(([k, v]) => `${k}: ${v}`).join(" · ")}
                    {" · "}{item.sku}
                  </p>
                  <p className="mt-0.5 text-xs text-neutral-500">
                    {item.quantity} × <PriceDisplay amount={item.unit_price} className="text-xs" />
                  </p>
                </div>
                <PriceDisplay amount={item.line_total} className="text-sm" />
              </li>
            ))}
          </ul>
          <div className="flex justify-between border-t border-neutral-100 px-5 py-3 text-sm font-semibold">
            <span>{t("seller.orders.subtotal")}</span>
            <PriceDisplay amount={order.seller_subtotal} data-testid="seller-order-subtotal" />
          </div>
        </section>

        <aside className="space-y-5">
          <section className="border border-neutral-200 bg-white p-5" data-testid="seller-order-actions">
            <h2 className="text-sm font-semibold">{t("seller.orderDetail.actions")}</h2>
            {!eligible ? (
              <p className="mt-3 border border-amber-300 bg-amber-50 p-3 text-xs font-medium text-amber-800" data-testid="seller-order-blocked">
                {t("seller.orderDetail.blockedUnpaid")}
              </p>
            ) : next ? (
              <div className="mt-3 space-y-3">
                {next === "shipped" ? (
                  <>
                    <input value={carrier} onChange={(e) => setCarrier(e.target.value)} placeholder={t("seller.orderDetail.carrier")} className={`${inputClass} w-full`} data-testid="fulfillment-carrier" maxLength={80} />
                    <input value={tracking} onChange={(e) => setTracking(e.target.value)} placeholder={t("seller.orderDetail.trackingNumber")} className={`${inputClass} w-full`} data-testid="fulfillment-tracking" maxLength={120} />
                  </>
                ) : null}
                <button
                  onClick={() => transition(next)}
                  disabled={busy}
                  data-testid={`fulfillment-mark-${next}`}
                  className="h-11 w-full bg-[#145A46] text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
                >
                  {t(`seller.orderDetail.mark_${next}`)}
                </button>
              </div>
            ) : (
              <p className="mt-3 text-xs text-neutral-400" data-testid="fulfillment-final">{t("seller.orderDetail.noActions")}</p>
            )}
            {order.fulfillment.tracking_number ? (
              <p className="mt-3 text-xs text-neutral-500" data-testid="fulfillment-tracking-display">
                {order.fulfillment.shipping_carrier ? `${order.fulfillment.shipping_carrier} · ` : ""}
                {order.fulfillment.tracking_number}
              </p>
            ) : null}
          </section>

          <section className="border border-neutral-200 bg-white p-5 text-sm" data-testid="seller-order-customer">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">{t("seller.orderDetail.customer")}</h2>
            <p className="mt-2 font-medium">{c.recipient_name} · {c.phone}</p>
            <p className="mt-1 text-xs text-neutral-500">
              {c.address_line_1}{c.address_line_2 ? `, ${c.address_line_2}` : ""}, {c.city}, {c.state_province} {c.postal_code}, {c.country_code}
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
