import { useEffect, useRef, useState } from "react";
import {
  cartSignature,
  handoffText,
  readHandoff,
  saveHandoff,
  telegramInquiryMessage,
  telegramShareUrl,
} from "@/lib/telegramHandoff";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Minus, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import {
  createTelegramCartInquiry,
  getTelegramCartInquiry,
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
  const busy = useRef(false);
  const refreshedAfterDelivery = useRef(null);
  const signature = cartSignature(cart, locale);
  const [handoff, setHandoff] = useState(null);
  const active = handoff?.signature === signature ? handoff : readHandoff(signature);
  const copy = handoffText[locale] || handoffText.en;
  const storeUsername = telegramStatusQuery.data?.store_username;
  const inquiryMessage = telegramInquiryMessage(active?.inquiry);
  const inquiryShareUrl = active?.inquiry
    ? telegramShareUrl(inquiryMessage, new URL("/", window.location.origin).toString())
    : null;
  const receipt = useQuery({
    queryKey: ["telegram-receipt", cart?.id, active?.inquiry?.reference],
    queryFn: () => getTelegramCartInquiry(active.inquiry.reference, guestCartMode),
    enabled: Boolean(active?.inquiry?.reference),
    refetchInterval: (query) => ["sent", "order_created", "expired"].includes(query.state.data?.status) ? false : 5000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const delivered = ["sent", "order_created"].includes(receipt.data?.status);
  useEffect(() => {
    const reference = active?.inquiry?.reference;
    if (delivered && reference && refreshedAfterDelivery.current !== reference) {
      refreshedAfterDelivery.current = reference;
      void refetchCart();
    }
  }, [active?.inquiry?.reference, delivered, refetchCart]);
  const telegramAvailable =
    telegramStatusQuery.isSuccess && telegramStatusQuery.data?.available === true;

  const handleConfirm = async () => {
    if (!telegramAvailable || busy.current || cartMutationsBlocked) return;
    busy.current = true;
    setOpeningTelegram(true);
    let attemptSignature = signature;
    try {
      // Re-read the server cart before creating a new inquiry. The visible
      // cart can be stale after Telegram was opened in another app/tab.
      // Keep an existing idempotency key on retries: the first request may
      // have succeeded even if its response was lost, and the server can
      // return that inquiry even after its submitted items leave the cart.
      const retryingAttempt = Boolean(active?.key);
      const freshCart = active?.inquiry || retryingAttempt
        ? cart
        : (await refetchCart({ throwOnError: true })).data;
      if (!active?.inquiry && !retryingAttempt && !freshCart?.items?.length) {
        toast.error(t("cart.confirmCartChanged"));
        return;
      }
      const currentSignature = retryingAttempt && active?.signature
        ? active.signature
        : cartSignature(freshCart || cart, locale);
      attemptSignature = currentSignature;
      const reusableAttempt = active?.signature === currentSignature ? active : null;
      const key = reusableAttempt?.key || (window.crypto?.randomUUID
        ? window.crypto.randomUUID()
        : Array.from(window.crypto.getRandomValues(new Uint8Array(16)))
            .map((value) => value.toString(16).padStart(2, "0"))
            .join(""));
      const attempt = reusableAttempt || { signature: currentSignature, key, until: Date.now() + 86400000 };
      saveHandoff(attempt);
      setHandoff(attempt);
      const inquiry = reusableAttempt?.inquiry || await createTelegramCartInquiry({
        locale,
        idempotencyKey: key,
        guest: guestCartMode,
      });
      const ready = { ...attempt, inquiry };
      const target = new URL(inquiry.telegram_url);
      const expectedUsername = storeUsername;
      if (
        target.origin !== "https://t.me" ||
        target.pathname.toLowerCase() !== `/${expectedUsername}`.toLowerCase()
      ) {
        throw new Error("invalid_telegram_destination");
      }
      const message = telegramInquiryMessage(inquiry);
      const shareUrl = telegramShareUrl(
        message,
        new URL("/", window.location.origin).toString()
      );
      if (!shareUrl) throw new Error("telegram_message_missing");
      saveHandoff(ready);
      setHandoff(ready);
      window.location.assign(shareUrl);
    } catch (error) {
      if (error.response?.status === 409) {
        const next = { signature: attemptSignature, key: window.crypto.randomUUID(), until: Date.now() + 86400000 };
        saveHandoff(next); setHandoff(next);
      }
      const detail = error.response?.data?.detail;
      if (detail?.error === "cart_empty") {
        try { await refetchCart({ throwOnError: true }); } catch { /* Keep the inquiry error visible. */ }
        toast.error(t("cart.confirmCartChanged"));
      } else if (error.response?.status === 429 || detail === "too_many_requests") {
        toast.error(t("cart.confirmRateLimited"));
      } else {
        toast.error(t("cart.confirmFailed"));
      }
    } finally {
      busy.current = false;
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
                <li key={item.id} data-testid={`cart-item-${item.id}`} className="flex min-w-0 gap-3 py-4 sm:gap-4">
                  <Link to={`/product/${item.slug}`} className="shrink-0">
                    <ImageWithFallback
                      src={item.image_url}
                      alt={name}
                      loading="lazy"
                      className="aspect-[3/4] w-20 bg-secondary object-cover sm:w-24"
                    />
                  </Link>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <Link
                          to={`/product/${item.slug}`}
                          className="break-words text-sm font-medium leading-snug hover:underline"
                        >
                          {name}
                        </Link>
                        <p className="mt-0.5 break-all text-xs text-muted-foreground">
                          {options}
                          {options ? " · " : ""}
                          {item.sku}
                        </p>
                        <p data-testid={`cart-preorder-${item.id}`} className="mt-1 text-xs font-medium text-primary">
                          {t("preorder.label")}
                        </p>
                        {item.availability === "pre_order" && item.size_available_for_new_orders === false ? (
                          <p data-testid={`cart-legacy-size-${item.id}`} className="mt-1 text-xs text-muted-foreground">
                            {t("cart.sizeNoLongerAvailable")}
                          </p>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        data-testid={`cart-remove-${item.id}`}
                        aria-label={t("cart.remove")}
                        disabled={cartMutationsBlocked || openingTelegram}
                        onClick={() => handleRemove(item.id)}
                        className="inline-flex h-11 w-11 shrink-0 items-center justify-center text-muted-foreground transition-colors hover:text-destructive"
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
                          disabled={item.quantity <= 1 || cartMutationsBlocked || openingTelegram}
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
                          disabled={item.quantity >= 99 || item.can_increase_quantity === false || cartMutationsBlocked || openingTelegram}
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
            {active?.inquiry ? (
              <div className="mt-4 space-y-3 rounded border border-border p-3 text-sm" aria-live="polite">
                <p>{delivered ? copy.sent : receipt.data?.status === "unknown" ? copy.unknown : receipt.data?.status === "expired" ? copy.expired : copy.waiting}</p>
                {!delivered && receipt.data?.status !== "expired" && storeUsername ? <p className="font-semibold">@{storeUsername}</p> : null}
                {!delivered && receipt.data?.status !== "expired" ? <>
                  <textarea aria-label={copy.copy} readOnly value={inquiryMessage} className="w-full rounded border p-2 text-xs" rows={4} />
                  {inquiryShareUrl ? <a className="block underline" href={inquiryShareUrl}>{copy.open}</a> : null}
                  <button type="button" className="underline" onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(inquiryMessage);
                      toast.success(copy.copied);
                    } catch { /* The selectable text above remains available. */ }
                  }}>{copy.copy}</button>
                </> : <button type="button" className="underline" onClick={() => {
                  const next = { signature, key: window.crypto.randomUUID(), until: Date.now() + 86400000 };
                  saveHandoff(next); setHandoff(next);
                }}>{copy.new}</button>}
                <p className="text-xs text-muted-foreground">{copy.retained}</p>
              </div>
            ) : null}
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
