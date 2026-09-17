import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { getAdminOrder, updateAdminOrderStatus } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, fmtMoney } from "./adminUtils";

const NEXT_STATUS = { paid: "processing", processing: "shipped", shipped: "delivered" };

export default function AdminOrderDetailPage() {
  const { orderNumber } = useParams();
  const queryClient = useQueryClient();
  const { data: order, isLoading } = useQuery({
    queryKey: ["admin-order", orderNumber],
    queryFn: () => getAdminOrder(orderNumber),
  });

  const advance = async () => {
    const next = NEXT_STATUS[order?.status];
    if (!next) return;
    try {
      await updateAdminOrderStatus(orderNumber, next);
      toast.success(`Order moved to ${next}`);
      queryClient.invalidateQueries({ queryKey: ["admin-order", orderNumber] });
      queryClient.invalidateQueries({ queryKey: ["admin-orders"] });
      queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
    } catch (err) {
      const d = err?.response?.data?.detail;
      const code = typeof d === "string" ? d : d?.error;
      toast.error(code === "payment_not_eligible" ? "Order payment is not eligible for fulfillment." : "Status update failed.");
    }
  };

  if (isLoading) {
    return <div data-testid="admin-order-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  }
  if (!order) {
    return <p className="text-sm text-neutral-500" data-testid="admin-order-missing">Order not found.</p>;
  }

  const addr = order.shipping_address || {};
  const next = order.payment_state === "paid" ? NEXT_STATUS[order.status] : null;

  return (
    <div data-testid="admin-order-detail">
      <Link to="/orders" className="inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-900" data-testid="order-back">
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        Back to orders
      </Link>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight" data-testid="order-number">{order.order_number}</h1>
          <p className="mt-1 text-xs text-neutral-500">{fmtDate(order.created_at)} · {order.email || "registered customer"}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill value={order.status} />
          <StatusPill value={order.payment_state} />
          {next ? (
            <button
              onClick={advance}
              data-testid="order-advance-status"
              className="h-10 bg-[#145A46] px-5 text-sm font-semibold text-white hover:opacity-90"
            >
              Mark as {next}
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[2fr_1fr]">
        <section className="border border-neutral-200 bg-white" data-testid="order-items">
          <h2 className="border-b border-neutral-200 px-5 py-3 text-sm font-semibold">Items</h2>
          <table className="w-full text-sm">
            <tbody>
              {(order.items || []).map((item, i) => (
                <tr key={i} className="border-b border-neutral-50" data-testid={`order-item-${item.sku}`}>
                  <td className="px-5 py-3">
                    <p className="font-medium">{item.product_name}</p>
                    <p className="text-xs text-neutral-400">
                      {item.sku}
                      {Object.keys(item.option_values || {}).length
                        ? ` · ${Object.entries(item.option_values).map(([k, v]) => `${k}: ${v}`).join(", ")}`
                        : ""}
                    </p>
                  </td>
                  <td className="px-5 py-3 text-neutral-500">{item.quantity} × {fmtMoney(item.unit_price, order.currency)}</td>
                  <td className="px-5 py-3 text-right font-medium">{fmtMoney(item.line_total, order.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="space-y-1 px-5 py-4 text-sm">
            <div className="flex justify-between text-neutral-500"><span>Subtotal</span><span>{fmtMoney(order.subtotal, order.currency)}</span></div>
            <div className="flex justify-between text-neutral-500"><span>Shipping ({order.shipping_method})</span><span>{fmtMoney(order.shipping_amount, order.currency)}</span></div>
            <div className="flex justify-between border-t border-neutral-100 pt-2 text-base font-semibold" data-testid="order-grand-total"><span>Total</span><span>{fmtMoney(order.grand_total, order.currency)}</span></div>
          </div>
        </section>

        <div className="space-y-6">
          <section className="border border-neutral-200 bg-white p-5" data-testid="order-shipping">
            <h2 className="text-sm font-semibold">Shipping address</h2>
            <address className="mt-3 text-sm not-italic leading-6 text-neutral-600">
              {addr.recipient_name}<br />
              {addr.phone}<br />
              {addr.address_line_1}<br />
              {addr.city}{addr.state_province ? `, ${addr.state_province}` : ""} {addr.postal_code}<br />
              {addr.country_code}
            </address>
          </section>

          <section className="border border-neutral-200 bg-white p-5" data-testid="order-payment">
            <h2 className="text-sm font-semibold">Payment</h2>
            {order.payment ? (
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between"><dt className="text-neutral-500">Status</dt><dd><StatusPill value={order.payment.status} /></dd></div>
                <div className="flex justify-between"><dt className="text-neutral-500">Amount</dt><dd className="font-medium">{fmtMoney(order.payment.amount, order.currency)}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-neutral-500">Transaction</dt><dd className="truncate font-mono text-xs">{order.payment.merchant_trans_id}</dd></div>
                {order.payment.paid_at ? <div className="flex justify-between"><dt className="text-neutral-500">Paid at</dt><dd>{fmtDate(order.payment.paid_at)}</dd></div> : null}
                {order.payment.failure_code ? <div className="flex justify-between"><dt className="text-neutral-500">Failure</dt><dd className="text-red-600">{order.payment.failure_code}</dd></div> : null}
                {order.payment.review_note ? <div className="border-t border-neutral-100 pt-2 text-xs text-neutral-500" data-testid="order-review-note">Review note: {order.payment.review_note}</div> : null}
              </dl>
            ) : (
              <p className="mt-3 text-sm text-neutral-400">No payment record.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
