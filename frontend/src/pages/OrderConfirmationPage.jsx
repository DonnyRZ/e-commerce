import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { getMyOrder, trackOrder } from "@/lib/api";
import PriceDisplay from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

export default function OrderConfirmationPage() {
  const { t } = useI18n();
  const { user, checking } = useAuth();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const orderNumber = searchParams.get("order") || "";
  const token = searchParams.get("token") || "";

  const orderQuery = useQuery({
    queryKey: ["order-confirmation", orderNumber],
    queryFn: () =>
      user ? getMyOrder(orderNumber) : trackOrder(orderNumber, token),
    enabled: !checking && Boolean(orderNumber) && (Boolean(user) || Boolean(token)),
    retry: false,
  });

  // payment success cleared the source cart server-side — sync the badge
  const paid = orderQuery.data?.payment_state === "paid";
  useEffect(() => {
    if (paid) queryClient.invalidateQueries({ queryKey: ["cart"] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paid]);

  if (checking || orderQuery.isLoading) {
    return (
      <div className="py-16" data-testid="confirm-loading">
        <Skeleton className="mx-auto h-10 w-64" />
        <Skeleton className="mx-auto mt-6 h-40 w-full max-w-lg" />
      </div>
    );
  }

  const order = orderQuery.data;
  if (orderQuery.isError || !order) {
    return (
      <div className="py-16 text-center" data-testid="confirm-invalid">
        <p className="text-sm text-muted-foreground">{t("mockPay.invalid")}</p>
        <Link
          to="/shop"
          className="mt-5 inline-flex h-11 items-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
        >
          {t("confirm.continue")}
        </Link>
      </div>
    );
  }

  return (
    <div className="py-12 lg:py-16" data-testid="order-confirmation">
      <div className="mx-auto max-w-xl text-center">
        <CheckCircle2
          className="mx-auto h-14 w-14 text-primary"
          aria-hidden="true"
        />
        <h1 className="mt-4 text-2xl font-semibold tracking-tight lg:text-3xl">
          {t("confirm.thanks")}
        </h1>
        <dl className="mx-auto mt-8 max-w-sm space-y-3 border border-border p-5 text-left text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">{t("confirm.orderNumber")}</dt>
            <dd className="font-semibold" data-testid="confirm-order-number">
              {order.order_number}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">{t("confirm.totalPaid")}</dt>
            <dd data-testid="confirm-total">
              <PriceDisplay amount={order.grand_total} />
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">{t("orders.paymentState")}</dt>
            <dd className="font-medium text-primary" data-testid="confirm-payment-state">
              {t(`orders.pay.${order.payment_state}`)}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">
          {t("confirm.emailNote", { email: order.email })}
        </p>
        {!user ? (
          <p className="mt-1 text-xs text-muted-foreground">
            {t("confirm.saveLink")}
          </p>
        ) : null}
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Link
            to="/shop"
            data-testid="confirm-continue"
            className="inline-flex h-11 items-center justify-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
          >
            {t("confirm.continue")}
          </Link>
          {user ? (
            <Link
              to="/orders"
              data-testid="confirm-view-orders"
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
