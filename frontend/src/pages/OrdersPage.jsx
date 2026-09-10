import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { getMyOrders } from "@/lib/api";
import EmptyState from "@/components/common/EmptyState";
import PriceDisplay, { LOCALE_TAGS } from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

export function StatusBadge({ value, kind, testId }) {
  const { t } = useI18n();
  const paid = value === "paid";
  const bad = ["cancelled", "failed", "expired"].includes(value);
  return (
    <span
      data-testid={testId}
      className={`inline-block px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
        paid
          ? "bg-primary text-primary-foreground"
          : bad
            ? "bg-destructive text-destructive-foreground"
            : "bg-secondary text-secondary-foreground"
      }`}
    >
      {t(`orders.${kind}.${value}`)}
    </span>
  );
}

export default function OrdersPage() {
  const { t, locale } = useI18n();
  const { user, checking } = useAuth();
  const ordersQuery = useQuery({
    queryKey: ["my-orders"],
    queryFn: getMyOrders,
    enabled: Boolean(user),
  });

  if (checking) {
    return (
      <div className="py-8" data-testid="orders-loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-32 w-full" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;

  const orders = ordersQuery.data || [];
  const tag = LOCALE_TAGS[locale] || "en-US";
  const fmtDate = (iso) =>
    new Intl.DateTimeFormat(tag, { dateStyle: "medium" }).format(new Date(iso));

  return (
    <div data-testid="orders-page" className="py-8 lg:py-12">
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("orders.title")}
      </h1>
      {ordersQuery.isLoading ? (
        <Skeleton className="mt-8 h-40 w-full" />
      ) : orders.length === 0 ? (
        <div data-testid="orders-empty">
          <EmptyState
            title={t("orders.empty")}
            description={t("orders.emptyHint")}
            action={
              <Link
                to="/shop"
                data-testid="orders-empty-cta"
                className="inline-flex h-11 items-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
              >
                {t("cart.emptyCta")}
              </Link>
            }
          />
        </div>
      ) : (
        <ul className="mt-8 divide-y divide-border border-y border-border" data-testid="orders-list">
          {orders.map((o) => (
            <li key={o.order_number}>
              <Link
                to={`/orders/${o.order_number}`}
                data-testid={`order-row-${o.order_number}`}
                className="flex flex-wrap items-center gap-x-6 gap-y-2 py-4 transition-colors hover:bg-secondary/50"
              >
                <span className="text-sm font-semibold">{o.order_number}</span>
                <span className="text-xs text-muted-foreground">
                  {fmtDate(o.created_at)}
                </span>
                <StatusBadge
                  value={o.payment_state}
                  kind="pay"
                  testId={`order-pay-${o.order_number}`}
                />
                <StatusBadge
                  value={o.status}
                  kind="state"
                  testId={`order-status-${o.order_number}`}
                />
                <span className="text-xs text-muted-foreground">
                  {t("orders.items", { count: o.item_count })}
                </span>
                <span className="ml-auto">
                  <PriceDisplay amount={o.grand_total} className="text-sm" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
