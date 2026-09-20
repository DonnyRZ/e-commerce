import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { useShop } from "@/lib/ShopContext";
import {
  getAddresses,
  getCheckoutOptions,
  getCheckoutQuote,
  placeOrder,
} from "@/lib/api";
import { pickLocalized } from "@/lib/localize";
import EmptyState from "@/components/common/EmptyState";
import PriceDisplay from "@/components/common/PriceDisplay";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";

const fieldClass =
  "h-11 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground";

const EMPTY_ADDR = {
  recipient_name: "",
  phone: "",
  address_line_1: "",
  address_line_2: "",
  city: "",
  state_province: "",
  postal_code: "",
  country_code: "UZ",
};

const newIdempotencyKey = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  if (globalThis.crypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
};

function AddressFields({ value, onChange, testPrefix }) {
  const { t } = useI18n();
  const set = (key) => (e) => onChange({ ...value, [key]: e.target.value });
  const fields = [
    ["recipient_name", t("auth.recipient")],
    ["phone", t("auth.phone")],
    ["address_line_1", t("auth.addressLine1")],
    ["address_line_2", t("auth.addressLine2")],
    ["city", t("auth.city")],
    ["state_province", t("auth.province")],
    ["postal_code", t("auth.postalCode")],
    ["country_code", t("auth.country")],
  ];
  const autocomplete = {
    recipient_name: "name",
    phone: "tel",
    address_line_1: "street-address",
    address_line_2: "address-line2",
    city: "address-level2",
    state_province: "address-level1",
    postal_code: "postal-code",
    country_code: "country",
  };
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {fields.map(([key, label]) => (
        <div
          key={key}
          className={key === "address_line_1" ? "sm:col-span-2" : ""}
        >
          <label
            htmlFor={`${testPrefix}-${key.replace(/_/g, "-")}`}
            className="mb-1 block text-xs font-medium text-muted-foreground"
          >
            {label}
          </label>
          <input
            id={`${testPrefix}-${key.replace(/_/g, "-")}`}
            data-testid={`${testPrefix}-${key.replace(/_/g, "-")}`}
            value={value[key] || ""}
            onChange={set(key)}
            required={key !== "address_line_2"}
            maxLength={key === "country_code" ? 2 : 255}
            autoComplete={autocomplete[key]}
            type={key === "phone" ? "tel" : "text"}
            className={fieldClass}
          />
        </div>
      ))}
    </div>
  );
}

export default function CheckoutPage() {
  const { t, locale } = useI18n();
  const { user } = useAuth();
  const { cart, cartLoading, guestCartMode } = useShop();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const idempotencyKey = useRef(newIdempotencyKey());
  const [email, setEmail] = useState("");
  const [addressMode, setAddressMode] = useState("new");
  const [savedAddressId, setSavedAddressId] = useState(null);
  const [addr, setAddr] = useState(EMPTY_ADDR);
  const [shippingMethod, setShippingMethod] = useState("standard");
  const [placing, setPlacing] = useState(false);

  const optionsQuery = useQuery({
    queryKey: ["checkout-options", guestCartMode ? "guest" : "customer"],
    queryFn: () => getCheckoutOptions({ guest: guestCartMode }),
  });
  // Keep the UI aligned with the server and fail closed if the status call
  // fails. The backend remains the final enforcement point.
  const checkoutEnabled =
    optionsQuery.isSuccess && optionsQuery.data?.checkout_enabled !== false;
  const addressesQuery = useQuery({
    queryKey: ["addresses", user?.id || "anonymous"],
    queryFn: getAddresses,
    enabled: user?.role === "customer",
  });
  const hasItems = Boolean(cart?.item_count);
  const quoteQuery = useQuery({
    queryKey: ["checkout-quote", guestCartMode ? "guest" : "customer", shippingMethod],
    queryFn: () => getCheckoutQuote(shippingMethod, { guest: guestCartMode }),
    enabled: hasItems && optionsQuery.isSuccess && checkoutEnabled,
    retry: false,
  });

  const addresses = addressesQuery.data || [];
  useEffect(() => {
    setSavedAddressId(null);
    setAddressMode("new");
    setAddr(EMPTY_ADDR);
    setEmail(user?.email || "");
  }, [user?.id, user?.email]);

  useEffect(() => {
    if (user?.role === "customer" && addresses.length && !savedAddressId) {
      const def = addresses.find((a) => a.is_default) || addresses[0];
      setSavedAddressId(def.id);
      setAddressMode("saved");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addressesQuery.data, user]);

  const submit = async (e) => {
    e.preventDefault();
    if (!checkoutEnabled) return;
    if (placing) return;
    setPlacing(true);
    try {
      const payload = {
        idempotency_key: idempotencyKey.current,
        shipping_method: shippingMethod,
        locale,
      };
      if (!user) payload.email = email;
      if (user && addressMode === "saved" && savedAddressId) {
        payload.saved_address_id = savedAddressId;
      } else {
        payload.address = addr;
      }
      const res = await placeOrder(payload, { guest: guestCartMode });
      // idempotency key is single-use per intended checkout — rotate after success
      idempotencyKey.current = newIdempotencyKey();
      const token = res.access_token
        ? `&token=${encodeURIComponent(res.access_token)}`
        : "";
      navigate(`/payment-pending?order=${encodeURIComponent(res.order_number)}${token}`);
    } catch (err) {
      const d = err?.response?.data?.detail;
      const code = typeof d === "string" ? d : d?.error;
      if (code === "unavailable_item") {
        toast.error(t("checkout.failed"));
        queryClient.invalidateQueries({ queryKey: ["cart"] });
        queryClient.invalidateQueries({ queryKey: ["checkout-quote"] });
      } else if (code === "empty_cart") {
        navigate("/cart");
      } else {
        toast.error(t("checkout.failed"));
      }
    } finally {
      setPlacing(false);
    }
  };

  if (cartLoading || optionsQuery.isLoading) {
    return (
      <div className="py-8" data-testid="checkout-loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-64 w-full" />
      </div>
    );
  }

  if (!hasItems) {
    return (
      <div data-testid="checkout-empty">
        <EmptyState
          title={t("checkout.empty")}
          action={
            <Link
              to="/cart"
              data-testid="checkout-empty-cta"
              className="inline-flex h-11 items-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
            >
              {t("checkout.emptyCta")}
            </Link>
          }
        />
      </div>
    );
  }

  if (!checkoutEnabled) {
    return (
      <div data-testid="checkout-disabled" className="py-8 lg:py-12">
        <EmptyState
          title={t("checkout.disabledTitle")}
          description={t("checkout.disabledBody")}
          action={
            <Link
              to="/shop"
              data-testid="checkout-disabled-cta"
              className="inline-flex h-11 items-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
            >
              {t("checkout.disabledCta")}
            </Link>
          }
        />
      </div>
    );
  }

  const options = optionsQuery.data;
  const quote = quoteQuery.data;
  const items = options?.items || cart?.items || [];

  return (
    <div data-testid="checkout-page" className="py-8 lg:py-12">
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("checkout.title")}
      </h1>
      <form
        onSubmit={submit}
        className="mt-8 grid gap-10 lg:grid-cols-[1fr_360px]"
      >
        <div className="space-y-8">
          <section data-testid="checkout-contact">
            <h2 className="text-sm font-semibold uppercase tracking-wide">
              {t("checkout.contact")}
            </h2>
            {user ? (
              <p className="mt-3 text-sm" data-testid="checkout-email-readonly">
                {user.email}
              </p>
            ) : (
              <div className="mt-3 max-w-md">
                <label htmlFor="checkout-email" className="mb-1 block text-xs font-medium text-muted-foreground">
                  {t("checkout.email")}
                </label>
                <input
                  id="checkout-email"
                  type="email"
                  required
                  data-testid="checkout-email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  className={fieldClass}
                />
              </div>
            )}
          </section>

          <section data-testid="checkout-address">
            <h2 className="text-sm font-semibold uppercase tracking-wide">
              {t("checkout.shippingAddress")}
            </h2>
            {user && addresses.length > 0 ? (
              <div className="mt-3 space-y-2">
                <p className="text-xs font-medium text-muted-foreground">
                  {t("checkout.savedAddresses")}
                </p>
                {addresses.map((a) => (
                  <label
                    key={a.id}
                    data-testid={`checkout-saved-address-${a.id}`}
                    className={`flex cursor-pointer gap-3 border p-3 text-sm ${
                      addressMode === "saved" && savedAddressId === a.id
                        ? "border-foreground"
                        : "border-border"
                    }`}
                  >
                    <input
                      type="radio"
                      name="address-mode"
                      checked={addressMode === "saved" && savedAddressId === a.id}
                      onChange={() => {
                        setAddressMode("saved");
                        setSavedAddressId(a.id);
                      }}
                      className="mt-1 accent-primary"
                    />
                    <span>
                      <span className="font-medium">
                        {a.recipient_name} · {a.phone}
                      </span>
                      <span className="block text-muted-foreground">
                        {a.address_line_1}
                        {a.address_line_2 ? `, ${a.address_line_2}` : ""},{" "}
                        {a.city}, {a.state_province} {a.postal_code},{" "}
                        {a.country_code}
                      </span>
                    </span>
                  </label>
                ))}
                <label
                  className="flex cursor-pointer items-center gap-3 border border-border p-3 text-sm"
                  data-testid="checkout-address-new-radio"
                >
                  <input
                    type="radio"
                    name="address-mode"
                    checked={addressMode === "new"}
                    onChange={() => setAddressMode("new")}
                    className="accent-primary"
                  />
                  {t("checkout.newAddress")}
                </label>
              </div>
            ) : null}
            {addressMode === "new" || !user || addresses.length === 0 ? (
              <div className="mt-3">
                <AddressFields
                  value={addr}
                  onChange={setAddr}
                  testPrefix="checkout-address"
                />
              </div>
            ) : null}
          </section>

          <section data-testid="checkout-shipping">
            <h2 className="text-sm font-semibold uppercase tracking-wide">
              {t("checkout.shippingMethod")}
            </h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {(options?.shipping_methods || []).map((m) => (
                <label
                  key={m.code}
                  data-testid={`checkout-shipping-${m.code}`}
                  className={`flex cursor-pointer items-center justify-between gap-3 border p-4 text-sm ${
                    shippingMethod === m.code
                      ? "border-foreground"
                      : "border-border"
                  }`}
                >
                  <span className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="shipping-method"
                      checked={shippingMethod === m.code}
                      onChange={() => setShippingMethod(m.code)}
                      className="accent-primary"
                    />
                    <span>
                      <span className="block font-medium">{m.label}</span>
                      <span className="text-xs text-muted-foreground">
                        {t("checkout.etaDays", { days: m.eta })}
                      </span>
                    </span>
                  </span>
                  {m.amount === 0 ? (
                    <span className="text-sm font-semibold text-primary">
                      {t("checkout.free")}
                    </span>
                  ) : (
                    <PriceDisplay amount={m.amount} className="text-sm" />
                  )}
                </label>
              ))}
            </div>
          </section>

        </div>

        <aside
          data-testid="checkout-summary"
          className="h-fit border border-border p-5 lg:sticky lg:top-28"
        >
          <h2 className="text-sm font-semibold uppercase tracking-wide">
            {t("checkout.orderSummary")}
          </h2>
          <ul className="mt-4 space-y-3">
            {items.map((item) => (
              <li key={item.id} className="flex gap-3" data-testid={`checkout-item-${item.id}`}>
                <ImageWithFallback
                  src={item.image_url}
                  alt=""
                  loading="lazy"
                  className="aspect-[3/4] w-12 bg-secondary object-cover"
                />
                <div className="flex-1 text-xs">
                  <p className="font-medium leading-snug">
                    {pickLocalized(item.translations, locale)}
                  </p>
                  <p className="mt-0.5 text-muted-foreground">
                    {Object.values(item.option_values || {}).join(" / ")} ×{" "}
                    {item.quantity}
                  </p>
                </div>
                <PriceDisplay amount={item.line_total} className="text-xs" />
              </li>
            ))}
          </ul>
          <div className="mt-5 space-y-2 border-t border-border pt-4 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                {t("checkout.subtotal")}
              </span>
              {quote ? (
                <PriceDisplay amount={quote.subtotal} data-testid="checkout-subtotal" />
              ) : (
                <Skeleton className="h-4 w-20" />
              )}
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                {t("checkout.shipping")}
              </span>
              {quote ? (
                quote.shipping_amount === 0 ? (
                  <span className="font-semibold text-primary" data-testid="checkout-shipping-free">
                    {t("checkout.free")}
                  </span>
                ) : (
                  <PriceDisplay
                    amount={quote.shipping_amount}
                    data-testid="checkout-shipping-amount"
                  />
                )
              ) : (
                <Skeleton className="h-4 w-20" />
              )}
            </div>
            <div className="flex justify-between border-t border-border pt-3 text-base font-semibold">
              <span>{t("checkout.total")}</span>
              {quote ? (
                <PriceDisplay
                  amount={quote.grand_total}
                  data-testid="checkout-grand-total"
                />
              ) : (
                <Skeleton className="h-5 w-24" />
              )}
            </div>
          </div>
          {quoteQuery.isError ? (
            <p
              data-testid="checkout-quote-error"
              className="mt-3 text-xs font-medium text-destructive"
            >
              {t("checkout.stockError")}
            </p>
          ) : null}
          <button
            type="submit"
            data-testid="checkout-place-order"
            disabled={placing || !quote || quoteQuery.isError}
            className="mt-5 flex h-12 w-full items-center justify-center bg-foreground text-sm font-semibold text-background transition-colors hover:bg-primary disabled:opacity-50"
          >
            {placing ? t("checkout.placing") : t("checkout.placeOrder")}
          </button>
        </aside>
      </form>
    </div>
  );
}
