import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { getAdminOrders } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, fmtMoney, inputClass } from "./adminUtils";

const ORDER_STATUSES = ["pending_payment", "payment_review", "paid", "supplier_shipping", "received_by_admin", "customer_shipping", "delivered", "processing", "shipped", "cancelled", "refunded"];
const PAYMENT_STATES = ["unpaid", "review", "pending", "pending_review", "paid", "rejected", "failed", "cancelled", "expired", "reconciliation_required", "refunded"];

export default function AdminOrdersPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const page = parseInt(params.get("page") || "1", 10);
  const status = params.get("status") || "";
  const paymentState = params.get("payment_state") || "";

  const { data, isLoading } = useQuery({
    queryKey: ["admin-orders", { q: params.get("q") || "", status, paymentState, page }],
    queryFn: () =>
      getAdminOrders({
        q: params.get("q") || undefined,
        status: status || undefined,
        payment_state: paymentState || undefined,
        page,
      }),
  });

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  };

  const items = data?.items || [];
  const total = data?.total || 0;
  const pageSize = data?.page_size || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div data-testid="admin-orders-page">
      <h1 className="text-xl font-semibold tracking-tight">Orders</h1>

      <div className="mt-5 flex flex-wrap gap-3">
        <form
          className="relative"
          onSubmit={(e) => {
            e.preventDefault();
            setFilter("q", q.trim());
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" aria-hidden="true" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Order number…"
            data-testid="orders-search"
            className={`${inputClass} w-56 pl-9`}
          />
        </form>
        <select value={status} onChange={(e) => setFilter("status", e.target.value)} className={`${inputClass} w-48`} data-testid="orders-status-filter">
          <option value="">All statuses</option>
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>{s.replaceAll("_", " ")}</option>
          ))}
        </select>
        <select value={paymentState} onChange={(e) => setFilter("payment_state", e.target.value)} className={`${inputClass} w-48`} data-testid="orders-payment-filter">
          <option value="">All payments</option>
          {PAYMENT_STATES.map((s) => (
            <option key={s} value={s}>{s.replaceAll("_", " ")}</option>
          ))}
        </select>
      </div>

      <div className="mt-5 overflow-x-auto border border-neutral-200 bg-white">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wider text-neutral-400">
              <th className="px-5 py-3 font-medium">Order</th>
              <th className="px-5 py-3 font-medium">Date</th>
              <th className="px-5 py-3 font-medium">Customer</th>
              <th className="px-5 py-3 font-medium">Items</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Payment</th>
              <th className="px-5 py-3 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}><td colSpan={7} className="px-5 py-3"><Skeleton className="h-5 w-full" /></td></tr>
                ))
              : items.map((o) => (
                  <tr key={o.order_number} className="border-b border-neutral-50 hover:bg-neutral-50" data-testid={`order-row-${o.order_number}`}>
                    <td className="px-5 py-3">
                      <Link to={`/orders/${o.order_number}`} className="font-medium text-[#145A46] hover:underline" data-testid={`order-open-${o.order_number}`}>
                        {o.order_number}
                      </Link>
                      {o.is_guest ? <span className="ml-2 text-[10px] uppercase tracking-wide text-neutral-400">guest</span> : null}
                    </td>
                    <td className="px-5 py-3 text-neutral-500">{fmtDate(o.created_at)}</td>
                    <td className="px-5 py-3 text-neutral-600">{o.recipient || o.email || "—"}</td>
                    <td className="px-5 py-3">{o.item_count}</td>
                    <td className="px-5 py-3"><StatusPill value={o.status} /></td>
                    <td className="px-5 py-3"><StatusPill value={o.payment_state} /></td>
                    <td className="px-5 py-3 text-right font-medium">{fmtMoney(o.grand_total, o.currency)}</td>
                  </tr>
                ))}
            {!isLoading && !items.length ? (
              <tr><td colSpan={7} className="px-5 py-10 text-center text-sm text-neutral-400" data-testid="orders-empty">No orders found.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-neutral-500" data-testid="orders-total">{total} orders</span>
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setFilter("page", String(page - 1))} data-testid="orders-prev" className="h-9 border border-neutral-300 px-4 text-xs font-medium disabled:opacity-40">
            Previous
          </button>
          <span className="flex h-9 items-center px-2 text-xs text-neutral-500" data-testid="orders-page-indicator">Page {page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setFilter("page", String(page + 1))} data-testid="orders-next" className="h-9 border border-neutral-300 px-4 text-xs font-medium disabled:opacity-40">
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
