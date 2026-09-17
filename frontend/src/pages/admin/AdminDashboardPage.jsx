import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { getAdminDashboard } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, fmtMoney } from "./adminUtils";

function StatCard({ label, value, testId, to }) {
  const body = (
    <div className="border border-neutral-200 bg-white p-5" data-testid={testId}>
      <p className="text-xs font-medium uppercase tracking-widest text-neutral-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export default function AdminDashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-dashboard"],
    queryFn: getAdminDashboard,
  });

  if (isLoading) {
    return (
      <div data-testid="admin-dashboard-loading">
        <Skeleton className="h-8 w-48" />
        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  const d = data || {};
  return (
    <div data-testid="admin-dashboard">
      <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard label="Sales total" value={fmtMoney(d.sales_total, d.currency)} testId="stat-sales-total" />
        <StatCard label="Orders needing action" value={d.orders_needing_action ?? 0} testId="stat-orders-action" to="/orders" />
        <StatCard label="Payment review" value={d.payment_review_count ?? 0} testId="stat-payment-review" to="/payments" />
        <StatCard label="Active products" value={`${d.active_products ?? 0} / ${d.total_products ?? 0}`} testId="stat-active-products" to="/products" />
        <StatCard label="Low stock variants" value={d.low_stock_variants ?? 0} testId="stat-low-stock" to="/products?inventory=low_stock" />
        <StatCard label="Out of stock variants" value={d.out_of_stock_variants ?? 0} testId="stat-out-of-stock" to="/products?inventory=out_of_stock" />
      </div>

      <section className="mt-8 border border-neutral-200 bg-white" data-testid="dashboard-status-breakdown">
        <h2 className="border-b border-neutral-200 px-5 py-3 text-sm font-semibold">Orders by status</h2>
        <div className="flex flex-wrap gap-2 px-5 py-4">
          {Object.entries(d.orders_by_status || {}).map(([status, count]) => (
            <span key={status} className="flex items-center gap-2 border border-neutral-200 px-3 py-1.5 text-xs" data-testid={`status-count-${status}`}>
              <StatusPill value={status} />
              <span className="font-semibold">{count}</span>
            </span>
          ))}
        </div>
      </section>

      <section className="mt-6 border border-neutral-200 bg-white" data-testid="dashboard-recent-orders">
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-3">
          <h2 className="text-sm font-semibold">Recent orders</h2>
          <Link to="/orders" className="inline-flex items-center gap-1 text-xs font-medium text-[#145A46] hover:underline" data-testid="dashboard-view-orders">
            View all <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-100 text-left text-xs uppercase tracking-wider text-neutral-400">
              <th className="px-5 py-2 font-medium">Order</th>
              <th className="px-5 py-2 font-medium">Date</th>
              <th className="px-5 py-2 font-medium">Status</th>
              <th className="px-5 py-2 font-medium">Payment</th>
              <th className="px-5 py-2 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {(d.recent_orders || []).map((o) => (
              <tr key={o.order_number} className="border-b border-neutral-50 hover:bg-neutral-50" data-testid={`recent-order-${o.order_number}`}>
                <td className="px-5 py-2.5">
                  <Link to={`/orders/${o.order_number}`} className="font-medium text-[#145A46] hover:underline">
                    {o.order_number}
                  </Link>
                </td>
                <td className="px-5 py-2.5 text-neutral-500">{fmtDate(o.created_at)}</td>
                <td className="px-5 py-2.5"><StatusPill value={o.status} /></td>
                <td className="px-5 py-2.5"><StatusPill value={o.payment_state} /></td>
                <td className="px-5 py-2.5 text-right font-medium">{fmtMoney(o.grand_total, o.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
