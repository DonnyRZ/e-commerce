import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Clock3 } from "lucide-react";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { getMyOrder, trackOrder } from "@/lib/api";
import PriceDisplay from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

export default function PaymentPendingPage() {
  const { t } = useI18n();
  const { user, checking } = useAuth();
  const [searchParams] = useSearchParams();
  const orderNumber = searchParams.get("order") || "";
  const token = searchParams.get("token") || "";

  const orderQuery = useQuery({
    queryKey: ["payment-status", orderNumber, token || user?.id || "guest"],
    queryFn: () =>
      user ? getMyOrder(orderNumber) : trackOrder(orderNumber, token),
    enabled: !checking && Boolean(orderNumber) && (Boolean(user) || Boolean(token)),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.payment_state === "paid" ? false : 5000,
  });

  if (orderQuery.data?.payment_state === "paid") {
    return <Navigate replace to={`/order-confirmation?${searchParams.toString()}`} />;
  }

  if (checking || orderQuery.isLoading) {
    return (
      <div className="py-16" data-testid="payment-pending-loading">
        <Skeleton className="mx-auto h-10 w-64" />
        <Skeleton className="mx-auto mt-6 h-40 w-full max-w-lg" />
      </div>
    );
  }

  const order = orderQuery.data;
  if (orderQuery.isError || !order) {
    return (
      <div className="py-16 text-center" data-testid="payment-pending-invalid">
        <AlertTriangle className="mx-auto h-12 w-12 text-destructive" aria-hidden="true" />
        <h1 className="mt-4 text-2xl font-semibold">{t("paymentPending.invalidTitle")}</h1>
        <p className="mx-auto mt-3 max-w-md text-sm text-muted-foreground">
          {t("paymentPending.invalidBody")}
        </p>
        <Link
          to="/shop"
          className="mt-6 inline-flex h-11 items-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
        >
          {t("confirm.continue")}
        </Link>
      </div>
    );
  }

  const needsReview = order.payment_state === "reconciliation_required";
  const failed = ["failed", "cancelled", "expired"].includes(order.payment_state);
  return (
    <div className="py-12 lg:py-16" data-testid="payment-pending">
      <div className="mx-auto max-w-xl text-center">
          {failed || needsReview ? (
          <AlertTriangle className="mx-auto h-14 w-14 text-destructive" aria-hidden="true" />
        ) : (
          <Clock3 className="mx-auto h-14 w-14 text-primary" aria-hidden="true" />
        )}
        <h1 className="mt-4 text-2xl font-semibold tracking-tight lg:text-3xl">
          {needsReview
            ? t("paymentPending.reviewTitle")
            : failed
              ? t("paymentPending.failedTitle")
              : t("paymentPending.title")}
        </h1>
        <p className="mx-auto mt-4 max-w-md text-sm text-muted-foreground">
          {needsReview
            ? t("paymentPending.reviewBody")
            : failed
              ? t("paymentPending.failedBody")
              : t("paymentPending.body")}
        </p>
        <dl className="mx-auto mt-8 max-w-sm space-y-3 border border-border p-5 text-left text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">{t("confirm.orderNumber")}</dt>
            <dd className="font-semibold">{order.order_number}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">{t("orders.total")}</dt>
            <dd><PriceDisplay amount={order.grand_total} /></dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">{t("orders.paymentState")}</dt>
            <dd className="font-medium" data-testid="payment-pending-state">
              {t(`orders.pay.${order.payment_state}`)}
            </dd>
          </div>
        </dl>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Link
            to="/shop"
            className="inline-flex h-11 items-center justify-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
          >
            {t("confirm.continue")}
          </Link>
          {user ? (
            <Link
              to="/orders"
              className="inline-flex h-11 items-center justify-center border border-border px-8 text-sm font-medium hover:border-foreground"
            >
              {t("confirm.viewOrders")}
            </Link>
          ) : null}
        </div>
      </div>
    </div>
  );
}
