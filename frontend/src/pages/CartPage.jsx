import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Minus, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import {
  createTelegramCartInquiry,
  getTelegramInquiryStatus,
} from "@/lib/api";
import { useShop } from "@/lib/ShopContext";
import { pickLocalized } from "@/lib/localize";
import EmptyState from "@/components/common/EmptyState";
import ErrorState from "@/components/common/ErrorState";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import PriceDisplay from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

export default function CartPage() {
  const { t, locale } = useI18n();
  const { cartMergeError, cartMergePending, retryCartMerge } = useAuth();
  const {
    cart,
    cartLoading,
    cartError,
    cartMutationsBlocked,
    guestCartMode,
    refetchCart,
    updateItem,
    removeItem,
  } = useShop();
  const telegramStatusQuery = useQuery({
    queryKey: ["telegram-inquiry-status"],
    queryFn: getTelegramInquiryStatus,
    enabled: Boolean(cart?.item_count) && !cartMutationsBlocked,
    staleTime: 60 * 1000,
    retry: false,
  });
  const [openingTelegram, setOpeningTelegram] = useState(false);
  const telegramAvailable =
    telegramStatusQuery.isSuccess && telegramStatusQuery.data?.available === true;

  const handleConfirm = async () => {
    if (!telegramAvailable || openingTelegram || cartMutationsBlocked) return;
    setOpeningTelegram(true);
    try {
      const key = window.crypto?.randomUUID
        ? window.crypto.randomUUID()
        : Array.from(window.crypto.getRandomValues(new Uint8Array(16)))
            .map((value) => value.toString(16).padStart(2, "0"))
            .join("");
      const inquiry = await createTelegramCartInquiry({
        locale,
        idempotencyKey: key,
        guest: guestCartMode,
      });
      const target = new URL(inquiry.telegram_url);
      const expectedUsername = telegramStatusQuery.data.store_username;
      if (
        target.origin !== "https://t.me" ||
        target.pathname.toLowerCase() !== `/${expectedUsername}`.toLowerCase()
      ) {
        throw new Error("invalid_telegram_destination");
      }
      window.location.assign(target.toString());
    } catch {
      toast.error(t("cart.confirmFailed"));
      setOpeningTelegram(false);
    }
  };

  const mergeNotice = cartMergeError || cartMergePending ? (
    <div role="alert" data-testid="cart-merge-error" className="mt-5 flex flex-wrap items-center justify-between gap-3 border border-destructive/40 bg-destructive/5 p-4 text-sm">
      <p>{t(cartMergePending ? "cart.mergePending" : "cart.mergeFailed")}</p>
      {cartMergeError ? (
        <button
          type="button"
          data-testid="cart-merge-retry"
          disabled={cartMergePending}
          onClick={retryCartMerge}
          className="h-9 border border-border px-4 font-medium disabled:opacity-50"
        >
          {cartMergePending ? t("common.loading") : t("common.retry")}
        </button>
      ) : null}
    </div>
  ) : null;

  if (cartLoading) {
    return (
      <div className="py-8" data-testid="cart-loading">
        {mergeNotice}
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-32 w-full" />
        <Skeleton className="mt-4 h-32 w-full" />
      </div>
    );
  }
  if (cartError) {
    return (
      <div className="py-8">
        {mergeNotice}
        <ErrorState message={t("errors.network")} onRetry={() => refetchCart()} />
      </div>
    );
  }

  const items = cart?.items || [];

  const handleQty = async (item, next) => {
    try {
      await updateItem(item.id, next);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.error === "quantity_limit") {
        toast.error(t("cart.quantityLimit", { count: d.maximum }));
      } else {
        toast.error(t("errors.generic"));
      }
    }
  };

  const handleRemove = async (itemId) => {
    try {
      await removeItem(itemId);
    } catch {
      toast.error(t("errors.generic"));
    }
  };

  return (
    <div data-testid="cart-page" className="py-8 lg:py-12">
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("cart.title")}
      </h1>
      {mergeNotice}
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
                    <ImageWithFallback
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
                        <p data-testid={`cart-preorder-${item.id}`} className="mt-1 text-xs font-medium text-primary">
                          {t("preorder.label")}
                        </p>
                      </div>
                      <button
                        type="button"
                        data-testid={`cart-remove-${item.id}`}
                        aria-label={t("cart.remove")}
                        disabled={cartMutationsBlocked}
                        onClick={() => handleRemove(item.id)}
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
                          disabled={item.quantity <= 1 || cartMutationsBlocked}
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
                          disabled={item.quantity >= 99 || cartMutationsBlocked}
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
            <p data-testid="cart-preorder-label" className="mb-3 text-sm font-medium text-primary">
              {t("preorder.label")}
            </p>
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
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {t("cart.confirmNote")}
            </p>
            <button
              type="button"
              data-testid="cart-telegram-confirm"
              disabled={!telegramAvailable || openingTelegram || cartMutationsBlocked}
              aria-busy={openingTelegram}
              onClick={handleConfirm}
              className="mt-5 flex h-12 w-full items-center justify-center bg-foreground text-sm font-semibold text-background transition-colors hover:bg-primary disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
            >
              {t("cart.confirm")}
            </button>
            {!telegramAvailable ? (
              <p data-testid="cart-telegram-unavailable" className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {t("cart.confirmUnavailable")}
              </p>
            ) : null}
          </aside>
        </div>
      )}
    </div>
  );
}
