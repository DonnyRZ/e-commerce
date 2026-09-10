import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical } from "lucide-react";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { getMyOrder, mockPay, trackOrder } from "@/lib/api";
import PriceDisplay from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

export default function MockPaymentPage() {
  const { t } = useI18n();
  const { user, checking } = useAuth();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const orderNumber = searchParams.get("order") || "";
  const merchantTransId = searchParams.get("payment") || "";
  const token = searchParams.get("token") || "";
  const [busy, setBusy] = useState(null);
  const [outcome, setOutcome] = useState(null);

  const orderQuery = useQuery({
    queryKey: ["mockpay-order", orderNumber],
    queryFn: () =>
      user ? getMyOrder(orderNumber) : trackOrder(orderNumber, token),
    enabled: !checking && Boolean(orderNumber) && (Boolean(user) || Boolean(token)),
    retry: false,
  });

  const act = async (scenario) => {
    if (busy) return;
    setBusy(scenario);
    try {
      const res = await mockPay({
        merchant_trans_id: merchantTransId,
        order_number: orderNumber,
        scenario,
        access_token: token || undefined,
      });
      if (res.payment_status === "paid") {
        queryClient.invalidateQueries({ queryKey: ["cart"] });
        navigate(
          `/order-confirmation?order=${orderNumber}${token ? `&token=${token}` : ""}`,
          { replace: true }
        );
      } else if (["prepared", "pending"].includes(res.payment_status)) {
        setOutcome("timeout");
      } else {
        setOutcome("failed");
      }
    } catch {
      setOutcome("invalid");
    } finally {
      setBusy(null);
    }
  };

  const order = orderQuery.data;

  return (
    <div className="py-10 lg:py-16" data-testid="mockpay-page">
      <div className="mx-auto max-w-lg border border-border">
        <div className="flex items-center gap-2 border-b border-border bg-amber-50 px-5 py-3 text-xs font-semibold uppercase tracking-wide text-amber-800">
          <FlaskConical className="h-4 w-4" aria-hidden="true" />
          <span data-testid="mockpay-badge">{t("mockPay.badge")}</span>
        </div>
        <div className="p-5 sm:p-8">
          <h1 className="text-xl font-semibold tracking-tight">
            {t("mockPay.title")}
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("mockPay.env")}
          </p>
          {orderQuery.isLoading || checking ? (
            <div className="mt-6 space-y-2" data-testid="mockpay-loading">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-8 w-56" />
            </div>
          ) : orderQuery.isError || !order ? (
            <div className="mt-6" data-testid="mockpay-invalid">
              <p className="flex items-center gap-2 text-sm font-medium text-destructive">
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                {t("mockPay.invalid")}
              </p>
              <Link
                to="/cart"
                data-testid="mockpay-invalid-back"
                className="mt-5 inline-flex h-11 items-center border border-border px-6 text-sm font-medium hover:border-foreground"
              >
                {t("checkout.emptyCta")}
              </Link>
            </div>
          ) : (
            <>
              <dl className="mt-6 space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">{t("mockPay.order")}</dt>
                  <dd className="font-medium" data-testid="mockpay-order-number">
                    {order.order_number}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">{t("mockPay.amount")}</dt>
                  <dd data-testid="mockpay-amount">
                    <PriceDisplay amount={order.grand_total} className="text-base" />
                  </dd>
                </div>
              </dl>
              {outcome === "failed" ? (
                <div className="mt-6 border border-destructive/40 bg-destructive/5 p-4" data-testid="mockpay-result-failed">
                  <p className="text-sm font-semibold text-destructive">
                    {t("mockPay.failedTitle")}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t("mockPay.failedBody")}
                  </p>
                  <Link
                    to="/checkout"
                    data-testid="mockpay-back-checkout"
                    className="mt-4 inline-flex h-10 items-center bg-foreground px-6 text-sm font-semibold text-background hover:bg-primary"
                  >
                    {t("mockPay.backToCheckout")}
                  </Link>
                </div>
              ) : outcome === "timeout" ? (
                <div className="mt-6 border border-amber-300 bg-amber-50 p-4" data-testid="mockpay-result-timeout">
                  <p className="text-sm font-semibold text-amber-800">
                    {t("mockPay.timeoutTitle")}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t("mockPay.timeoutBody")}
                  </p>
                </div>
              ) : outcome === "invalid" ? (
                <p className="mt-6 text-sm font-medium text-destructive" data-testid="mockpay-result-invalid">
                  {t("mockPay.invalid")}
                </p>
              ) : (
                <div className="mt-6 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    data-testid="mockpay-success"
                    disabled={Boolean(busy)}
                    onClick={() => act("SUCCESS")}
                    className="h-11 bg-primary text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    {busy === "SUCCESS" ? t("mockPay.processing") : t("mockPay.success")}
                  </button>
                  <button
                    type="button"
                    data-testid="mockpay-failure"
                    disabled={Boolean(busy)}
                    onClick={() => act("FAILED")}
                    className="h-11 border border-destructive text-sm font-semibold text-destructive transition-colors hover:bg-destructive hover:text-destructive-foreground disabled:opacity-50"
                  >
                    {t("mockPay.failure")}
                  </button>
                  <button
                    type="button"
                    data-testid="mockpay-cancel"
                    disabled={Boolean(busy)}
                    onClick={() => act("CANCELLED")}
                    className="h-11 border border-border text-sm font-medium transition-colors hover:border-foreground disabled:opacity-50"
                  >
                    {t("mockPay.cancel")}
                  </button>
                  <button
                    type="button"
                    data-testid="mockpay-timeout"
                    disabled={Boolean(busy)}
                    onClick={() => act("TIMEOUT")}
                    className="h-11 border border-border text-sm font-medium transition-colors hover:border-foreground disabled:opacity-50"
                  >
                    {t("mockPay.timeout")}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
