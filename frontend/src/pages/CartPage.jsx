import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Minus, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { getCheckoutOptions } from "@/lib/api";
import { useShop } from "@/lib/ShopContext";
import { pickLocalized } from "@/lib/localize";
import EmptyState from "@/components/common/EmptyState";
import ErrorState from "@/components/common/ErrorState";
import PriceDisplay from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

export default function CartPage() {
  const { t, locale } = useI18n();
  const { cart, cartLoading, cartError, refetchCart, updateItem, removeItem } = useShop();
  const checkoutOptionsQuery = useQuery({
    queryKey: ["checkout-options"],
    queryFn: getCheckoutOptions,
    enabled: Boolean(cart?.item_count),
    staleTime: 60 * 1000,
    retry: false,
  });
  // Fail closed if the backend status cannot be read. The API also blocks
  // checkout server-side, but the cart should not advertise a dead CTA.
  const checkoutEnabled =
    checkoutOptionsQuery.isSuccess &&
    checkoutOptionsQuery.data?.checkout_enabled !== false;

  if (cartLoading) {
    return (
      <div className="py-8" data-testid="cart-loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-32 w-full" />
        <Skeleton className="mt-4 h-32 w-full" />
      </div>
    );
  }
  if (cartError) {
    return <ErrorState message={t("errors.network")} onRetry={() => refetchCart()} />;
  }

  const items = cart?.items || [];

  const handleQty = async (item, next) => {
    try {
      await updateItem(item.id, next);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.error === "insufficient_stock") {
        toast.error(t("cart.exceedsStock", { count: d.available }));
      } else {
        toast.error(t("errors.generic"));
      }
    }
  };

  return (
    <div data-testid="cart-page" className="py-8 lg:py-12">
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("cart.title")}
      </h1>
      {items.length === 0 ? (
        <div data-testid="cart-empty">
          <EmptyState
            title={t("cart.empty")}
            description={t("cart.emptyHint")}
            action={
              <Link
                to="/shop"
                data-testid="cart-empty-cta"
                className="inline-flex h-11 items-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
              >
                {t("cart.emptyCta")}
              </Link>
            }
          />
        </div>
      ) : (
        <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_320px]">
          <ul className="divide-y divide-border border-y border-border">
            {items.map((item) => {
              const name = pickLocalized(item.translations, locale);
              const options = Object.values(item.option_values || {}).join(" / ");
              return (
                <li key={item.id} data-testid={`cart-item-${item.id}`} className="flex gap-4 py-4">
                  <Link to={`/product/${item.slug}`} className="shrink-0">
                    <img
                      src={item.image_url}
                      alt={name}
                      loading="lazy"
                      className="aspect-[3/4] w-20 bg-secondary object-cover sm:w-24"
                    />
                  </Link>
                  <div className="flex flex-1 flex-col">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Link
                          to={`/product/${item.slug}`}
                          className="text-sm font-medium leading-snug hover:underline"
                        >
                          {name}
                        </Link>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {options}
                          {options ? " · " : ""}
                          {item.sku}
                        </p>
                        {item.availability === "out_of_stock" || item.availability === "unavailable" ? (
                          <p data-testid={`cart-oos-${item.id}`} className="mt-1 text-xs font-medium text-destructive">
                            {t("product.outOfStock")}
                          </p>
                        ) : item.availability === "exceeds_stock" ? (
                          <p data-testid={`cart-exceeds-${item.id}`} className="mt-1 text-xs font-medium text-destructive">
                            {t("cart.exceedsStock", { count: item.stock_quantity })}
                          </p>
                        ) : item.availability === "low_stock" ? (
                          <p className="mt-1 text-xs font-medium text-primary">
                            {t("pdp.onlyLeft", { count: item.stock_quantity })}
                          </p>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        data-testid={`cart-remove-${item.id}`}
                        aria-label={t("cart.remove")}
                        onClick={() => removeItem(item.id)}
                        className="text-muted-foreground transition-colors hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                    <div className="mt-auto flex items-end justify-between pt-3">
                      <div className="flex items-center border border-border" data-testid={`cart-qty-${item.id}`}>
                        <button
                          type="button"
                          data-testid={`cart-qty-minus-${item.id}`}
                          aria-label="Decrease quantity"
                          disabled={item.quantity <= 1}
                          onClick={() => handleQty(item, item.quantity - 1)}
                          className="inline-flex h-9 w-9 items-center justify-center disabled:opacity-30"
                        >
                          <Minus className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                        <span className="w-9 text-center text-sm font-medium">
                          {item.quantity}
                        </span>
                        <button
                          type="button"
                          data-testid={`cart-qty-plus-${item.id}`}
                          aria-label="Increase quantity"
                          disabled={item.quantity >= item.stock_quantity}
                          onClick={() => handleQty(item, item.quantity + 1)}
                          className="inline-flex h-9 w-9 items-center justify-center disabled:opacity-30"
                        >
                          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>
                      <PriceDisplay
                        amount={item.line_total}
                        compareAt={
                          item.compare_at_price
                            ? item.compare_at_price * item.quantity
                            : null
                        }
                        className="text-sm"
                      />
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
          <aside data-testid="cart-summary" className="h-fit border border-border p-5 lg:sticky lg:top-28">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{t("cart.subtotal")}</span>
              <PriceDisplay
                amount={cart.subtotal}
                className="text-lg"
                data-testid="cart-subtotal"
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {t("cart.shippingNote")}
            </p>
            {checkoutEnabled ? (
              <Link
                to="/checkout"
                data-testid="cart-checkout-cta"
                className="mt-5 flex h-12 items-center justify-center bg-foreground text-sm font-semibold text-background transition-colors hover:bg-primary"
              >
                {t("cart.checkout")}
              </Link>
            ) : (
              <div className="mt-5 space-y-2">
                <button
                  type="button"
                  data-testid="cart-checkout-disabled"
                  disabled
                  className="flex h-12 w-full items-center justify-center bg-muted text-sm font-semibold text-muted-foreground"
                >
                  {t("cart.checkoutUnavailable")}
                </button>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t("cart.checkoutUnavailableBody")}
                </p>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
