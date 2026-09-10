import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, PackageX, ClipboardList, Package, Banknote } from "lucide-react";
import { useI18n } from "@/i18n";
import { getSellerDashboard } from "@/lib/api";
import PriceDisplay from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

function StatCard({ icon: Icon, label, value, testId, to, tone }) {
  const inner = (
    <div className="flex items-center gap-4 border border-neutral-200 bg-white p-5">
      <div
        className={`flex h-10 w-10 items-center justify-center rounded-sm ${
          tone === "warn" ? "bg-amber-50 text-amber-700" : tone === "danger" ? "bg-red-50 text-red-700" : "bg-[#145A46]/5 text-[#145A46]"
        }`}
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <div>
        <p className="text-2xl font-semibold tabular-nums" data-testid={testId}>{value}</p>
        <p className="text-xs text-neutral-500">{label}</p>
      </div>
    </div>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}

export default function SellerDashboardPage() {
  const { t } = useI18n();
  const dashQuery = useQuery({ queryKey: ["seller-dashboard"], queryFn: getSellerDashboard });

  if (dashQuery.isLoading) {
    return (
      <div data-testid="seller-dashboard-loading">
        <Skeleton className="h-8 w-48" />
        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      </div>
    );
  }
  const d = dashQuery.data;

  return (
    <div data-testid="seller-dashboard">
      <h1 className="text-xl font-semibold tracking-tight">{t("seller.dashboard.title")}</h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Package} label={t("seller.dashboard.activeProducts")} value={d.active_products} testId="dash-active-products" to="/seller/products" />
        <StatCard icon={AlertTriangle} label={t("seller.dashboard.lowStock")} value={d.low_stock_variants} testId="dash-low-stock" to="/seller/inventory" tone="warn" />
        <StatCard icon={PackageX} label={t("seller.dashboard.outOfStock")} value={d.out_of_stock_variants} testId="dash-oos" to="/seller/inventory" tone="danger" />
        <StatCard icon={ClipboardList} label={t("seller.dashboard.needsAction")} value={d.pending_fulfillments + d.processing_fulfillments} testId="dash-needs-action" to="/seller/orders" />
      </div>

      <div className="mt-4 border border-neutral-200 bg-white p-5" data-testid="dash-sales">
        <div className="flex items-center gap-3">
          <Banknote className="h-5 w-5 text-[#145A46]" aria-hidden="true" />
          <div>
            <p className="text-xs text-neutral-500">{t("seller.dashboard.salesTotal")}</p>
            <PriceDisplay amount={d.sales_total} data-testid="dash-sales-total" className="text-lg font-semibold" />
          </div>
          <div className="ml-8">
            <p className="text-xs text-neutral-500">{t("seller.dashboard.salesOrders")}</p>
            <p className="text-lg font-semibold tabular-nums" data-testid="dash-sales-orders">{d.sales_order_count}</p>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-neutral-400">{t("seller.dashboard.salesNote")}</p>
      </div>

      <div className="mt-6 border border-neutral-200 bg-white" data-testid="dash-recent-orders">
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-3">
          <h2 className="text-sm font-semibold">{t("seller.dashboard.recentOrders")}</h2>
          <Link to="/seller/orders" className="text-xs font-medium text-[#145A46] hover:underline" data-testid="dash-all-orders">
            {t("seller.dashboard.viewAll")}
          </Link>
        </div>
        {d.recent_orders.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-neutral-400" data-testid="dash-no-orders">
            {t("seller.orders.empty")}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-100 text-left text-xs text-neutral-400">
                <th className="px-5 py-2 font-medium">{t("seller.orders.order")}</th>
                <th className="px-5 py-2 font-medium">{t("seller.orders.payment")}</th>
                <th className="px-5 py-2 font-medium">{t("seller.orders.fulfillment")}</th>
                <th className="px-5 py-2 text-right font-medium">{t("seller.orders.subtotal")}</th>
              </tr>
            </thead>
            <tbody>
              {d.recent_orders.map((o) => (
                <tr key={o.order_number} className="border-b border-neutral-50 last:border-0 hover:bg-neutral-50">
                  <td className="px-5 py-2.5">
                    <Link to={`/seller/orders/${o.order_number}`} className="font-medium text-[#145A46] hover:underline" data-testid={`dash-order-${o.order_number}`}>
                      {o.order_number}
                    </Link>
                  </td>
                  <td className="px-5 py-2.5">
                    <span className={`inline-block px-2 py-0.5 text-[11px] font-semibold uppercase ${o.payment_state === "paid" ? "bg-[#145A46] text-white" : "bg-neutral-200 text-neutral-600"}`}>
                      {t(`orders.pay.${o.payment_state}`)}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-xs text-neutral-600">{t(`seller.fulfillment.${o.fulfillment_status}`)}</td>
                  <td className="px-5 py-2.5 text-right"><PriceDisplay amount={o.seller_subtotal} className="text-xs" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
