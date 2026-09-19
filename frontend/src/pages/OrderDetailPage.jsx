import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { getMyOrder } from "@/lib/api";
import PriceDisplay, { LOCALE_TAGS } from "@/components/common/PriceDisplay";
import { StatusBadge } from "@/pages/OrdersPage";
import { Skeleton } from "@/components/ui/skeleton";
import ImageWithFallback from "@/components/common/ImageWithFallback";

export default function OrderDetailPage() {
  const { t, locale } = useI18n();
  const { user, checking } = useAuth();
  const { orderNumber } = useParams();
  const location = useLocation();
  const orderQuery = useQuery({
    queryKey: ["my-order", user?.id || "anonymous", orderNumber],
    queryFn: () => getMyOrder(orderNumber),
    enabled: user?.role === "customer",
    retry: false,
  });

  if (checking) {
    return (
      <div className="py-8" data-testid="order-detail-loading">
        <Skeleton className="h-8 w-48" />
      </div>
    );
  }
  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ returnTo: `${location.pathname}${location.search}` }}
      />
    );
  }
  if (user.role !== "customer") {
    return user.role === "admin" ? (
      <Navigate to="/admin/" replace />
    ) : (
      <Navigate
        to="/login"
        replace
        state={{ returnTo: `${location.pathname}${location.search}` }}
      />
    );
  }

  if (orderQuery.isError) {
    return (
      <div className="py-16 text-center" data-testid="order-detail-notfound">
        <p className="text-sm text-muted-foreground">{t("errors.notFound")}</p>
        <Link
          to="/orders"
          className="mt-5 inline-flex h-11 items-center border border-border px-8 text-sm font-medium hover:border-foreground"
        >
          {t("orders.backToOrders")}
        </Link>
      </div>
    );
  }

  const order = orderQuery.data;
  if (!order) {
    return (
      <div className="py-8" data-testid="order-detail-loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-64 w-full" />
      </div>
    );
  }

  const tag = LOCALE_TAGS[locale] || "en-US";
  const a = order.shipping_address || {};

  return (
    <div data-testid="order-detail" className="py-8 lg:py-12">
      <Link
        to="/orders"
        data-testid="order-detail-back"
        className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        {t("orders.backToOrders")}
      </Link>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-2xl font-semibold tracking-tight" data-testid="order-detail-number">
          {t("orders.detailTitle")} {order.order_number}
        </h1>
        <StatusBadge value={order.payment_state} kind="pay" testId="order-detail-pay" />
        <StatusBadge value={order.status} kind="state" testId="order-detail-status" />
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        {new Intl.DateTimeFormat(tag, { dateStyle: "medium" }).format(
          new Date(order.created_at)
        )}{" "}
        · {order.email}
      </p>

      {order.timeline?.length ? (
        <section className="mt-6 border border-border bg-secondary/30 p-5" data-testid="customer-order-timeline">
          <h2 className="text-sm font-semibold">{t("orders.timeline")}</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {order.timeline.map((event) => (
              <div key={event.stage} className={`flex items-start gap-2 text-xs ${event.status === "completed" || event.status === "current" ? "text-primary" : "text-muted-foreground"}`}>
                <span className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${event.status === "completed" ? "bg-primary" : event.status === "current" ? "border-2 border-primary bg-background" : "bg-border"}`} />
                <div>
                  <p className="font-medium">{t(`orders.state.${event.stage}`)}</p>
                  {event.expected_at ? <p className="mt-1 text-muted-foreground">{t("orders.expectedBy")} {new Intl.DateTimeFormat(tag, { dateStyle: "medium" }).format(new Date(event.expected_at))}</p> : null}
                  {event.tracking_number ? <p className="mt-1 text-muted-foreground">{event.tracking_number}</p> : null}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_320px]">
        <ul className="divide-y divide-border border-y border-border">
          {order.items.map((item) => (
            <li
              key={item.sku}
              data-testid={`order-item-${item.sku}`}
              className="flex gap-4 py-4"
            >
              {item.image_url ? (
                <ImageWithFallback
                  src={item.image_url}
                  alt=""
                  loading="lazy"
                  className="aspect-[3/4] w-16 bg-secondary object-cover"
                />
              ) : null}
              <div className="flex-1">
                <p className="text-sm font-medium">{item.product_name}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {Object.values(item.option_values || {}).join(" / ")}
                  {" · "}
                  {item.sku}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {item.quantity} × <PriceDisplay amount={item.unit_price} className="text-xs" />
                </p>
              </div>
              <PriceDisplay amount={item.line_total} className="text-sm" />
            </li>
          ))}
        </ul>

        <aside className="h-fit space-y-6">
          <div className="border border-border p-5 text-sm" data-testid="order-totals">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("orders.subtotal")}</span>
              <PriceDisplay amount={order.subtotal} data-testid="order-subtotal" />
            </div>
            <div className="mt-2 flex justify-between">
              <span className="text-muted-foreground">{t("orders.shipping")}</span>
              {order.shipping_amount === 0 ? (
                <span className="font-semibold text-primary">{t("checkout.free")}</span>
              ) : (
                <PriceDisplay amount={order.shipping_amount} data-testid="order-shipping" />
              )}
            </div>
            <div className="mt-3 flex justify-between border-t border-border pt-3 text-base font-semibold">
              <span>{t("orders.total")}</span>
              <PriceDisplay amount={order.grand_total} data-testid="order-grand-total" />
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {t("orders.shippingMethod")}: {order.shipping_method}
            </p>
          </div>
          <div className="border border-border p-5 text-sm" data-testid="order-address">
            <h2 className="text-xs font-semibold uppercase tracking-wide">
              {t("orders.shippingAddress")}
            </h2>
            <p className="mt-2 font-medium">
              {a.recipient_name} · {a.phone}
            </p>
            <p className="mt-1 text-muted-foreground">
              {a.address_line_1}
              {a.address_line_2 ? `, ${a.address_line_2}` : ""}, {a.city},{" "}
              {a.state_province} {a.postal_code}, {a.country_code}
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
