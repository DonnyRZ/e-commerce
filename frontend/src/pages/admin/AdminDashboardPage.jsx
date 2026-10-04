import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, RefreshCw } from "lucide-react";
import { getAdminDashboard } from "@/lib/api";
import { useI18n } from "@/i18n";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtMoney, StatusPill } from "./adminUtils";

const WORKFLOW_STAGES = [
  "inquiry",
  "payment",
  "paid",
  "supplier_shipping",
  "received_by_admin",
  "customer_shipping",
  "delivered",
];

function StatCard({ label, value, testId, to }) {
  const body = (
    <div className="border border-neutral-200 bg-white p-5" data-testid={testId}>
      <p className="text-xs font-medium uppercase tracking-widest text-neutral-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

function DashboardError({ onRetry, isRetrying, t }) {
  return (
    <div className="border border-red-200 bg-red-50 p-6" data-testid="admin-dashboard-error">
      <h1 className="text-xl font-semibold text-red-900">{t("seller.dashboard.errorTitle")}</h1>
      <p className="mt-2 text-sm text-red-800">{t("seller.dashboard.errorDescription")}</p>
      <button
        type="button"
        onClick={onRetry}
        disabled={isRetrying}
        className="mt-4 inline-flex h-10 items-center gap-2 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-60"
        data-testid="admin-dashboard-retry"
      >
        <RefreshCw className={`h-4 w-4 ${isRetrying ? "animate-spin" : ""}`} aria-hidden="true" />
        {t("seller.dashboard.retry")}
      </button>
    </div>
  );
}

export default function AdminDashboardPage() {
  const { t } = useI18n();
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["admin-dashboard"],
    queryFn: getAdminDashboard,
  });

  if (isLoading) {
    return (
      <div data-testid="admin-dashboard-loading">
        <Skeleton className="h-8 w-48" />
        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      </div>
    );
  }

  if (isError) {
    return <DashboardError onRetry={refetch} isRetrying={isFetching} t={t} />;
  }

  const d = data || {};
  const workflowCounts = d.workflow_counts || {};

  return (
    <div data-testid="admin-dashboard">
      <h1 className="text-xl font-semibold tracking-tight">{t("seller.dashboard.title")}</h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard label={t("seller.dashboard.salesTotal")} value={fmtMoney(d.sales_total, d.currency)} testId="stat-sales-total" />
        <StatCard label={t("seller.dashboard.needsAction")} value={d.orders_needing_action ?? 0} testId="stat-orders-action" to="/orders?stage=actionable" />
        <StatCard label={t("seller.dashboard.paymentReview")} value={d.payment_count ?? 0} testId="stat-payment-review" to="/orders?stage=payment" />
        <StatCard label={t("seller.dashboard.activeProducts")} value={`${d.active_products ?? 0} / ${d.total_products ?? 0}`} testId="stat-active-products" to="/products" />
        <StatCard label={t("seller.dashboard.openInquiries")} value={d.open_inquiries ?? 0} testId="stat-open-inquiries" to="/orders?stage=inquiry" />
        <StatCard label={t("seller.dashboard.preordersInProgress")} value={d.preorders_in_progress ?? 0} testId="stat-preorders-progress" to="/orders" />
      </div>

      <section className="mt-8 border border-neutral-200 bg-white" data-testid="dashboard-status-breakdown">
        <h2 className="border-b border-neutral-200 px-5 py-3 text-sm font-semibold">{t("seller.dashboard.ordersByStatus")}</h2>
        <div className="grid gap-2 p-5 sm:grid-cols-2 lg:grid-cols-4">
          {WORKFLOW_STAGES.map((stage) => (
            <Link
              key={stage}
              to={`/orders?stage=${stage}`}
              className="flex items-center justify-between gap-3 border border-neutral-200 px-3 py-2 text-xs hover:border-[#145A46]"
              data-testid={`status-count-${stage}`}
            >
              <span className="min-w-0 text-neutral-700">{t(`seller.dashboard.status.${stage}`)}</span>
              <span className="shrink-0 font-semibold">{workflowCounts[stage] ?? 0}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="mt-6 border border-neutral-200 bg-white" data-testid="dashboard-recent-orders">
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-3">
          <h2 className="text-sm font-semibold">{t("seller.dashboard.recentOrders")}</h2>
          <Link to="/orders" className="inline-flex items-center gap-1 text-xs font-medium text-[#145A46] hover:underline" data-testid="dashboard-view-orders">
            {t("seller.dashboard.viewAll")} <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        <div className="space-y-3 p-3 md:hidden" data-testid="dashboard-recent-orders-mobile">
          {(d.recent_orders || []).map((o) => (
            <article key={o.order_number} className="rounded-lg border border-neutral-200 p-3" data-testid={`recent-order-mobile-${o.order_number}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link to={`/orders/${o.order_number}`} className="break-all font-semibold text-[#145A46] hover:underline" data-testid={`recent-order-mobile-link-${o.order_number}`}>{o.order_number}</Link>
                <span className="text-xs font-semibold">{fmtMoney(o.grand_total, o.currency)}</span>
              </div>
              <p className="mt-1 text-xs text-neutral-500">{fmtDate(o.created_at)}</p>
              <div className="mt-2 flex flex-wrap gap-2"><StatusPill value={o.status} /><StatusPill value={o.payment_state} /></div>
            </article>
          ))}
          {!d.recent_orders?.length ? <p className="px-2 py-8 text-center text-sm text-neutral-500">{t("seller.dashboard.noRecentOrders")}</p> : null}
        </div>
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full min-w-[620px] text-sm">
            <thead>
              <tr className="border-b border-neutral-100 text-left text-xs uppercase tracking-wider text-neutral-400">
                <th className="px-5 py-2 font-medium">{t("seller.dashboard.order")}</th>
                <th className="px-5 py-2 font-medium">{t("seller.dashboard.date")}</th>
                <th className="px-5 py-2 font-medium">{t("seller.dashboard.status")}</th>
                <th className="px-5 py-2 font-medium">{t("seller.dashboard.payment")}</th>
                <th className="px-5 py-2 text-right font-medium">{t("seller.dashboard.total")}</th>
              </tr>
            </thead>
            <tbody>
              {(d.recent_orders || []).map((o) => (
                <tr key={o.order_number} className="border-b border-neutral-50 hover:bg-neutral-50" data-testid={`recent-order-${o.order_number}`}>
                  <td className="px-5 py-2.5"><Link to={`/orders/${o.order_number}`} className="font-medium text-[#145A46] hover:underline">{o.order_number}</Link></td>
                  <td className="px-5 py-2.5 text-neutral-500">{fmtDate(o.created_at)}</td>
                  <td className="px-5 py-2.5"><StatusPill value={o.status} /></td>
                  <td className="px-5 py-2.5"><StatusPill value={o.payment_state} /></td>
                  <td className="px-5 py-2.5 text-right font-medium">{fmtMoney(o.grand_total, o.currency)}</td>
                </tr>
              ))}
              {!d.recent_orders?.length ? (
                <tr><td colSpan="5" className="px-5 py-10 text-center text-sm text-neutral-500">{t("seller.dashboard.noRecentOrders")}</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
