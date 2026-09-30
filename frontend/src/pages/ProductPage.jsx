import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Heart, Minus, Plus, ShoppingBag } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { getProduct } from "@/lib/api";
import { useShop } from "@/lib/ShopContext";
import { colorHex, pickLocalized } from "@/lib/localize";
import EmptyState from "@/components/common/EmptyState";
import ErrorState from "@/components/common/ErrorState";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import PriceDisplay from "@/components/common/PriceDisplay";
import SizeGuide from "@/components/pdp/SizeGuide";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

function PdpSkeleton() {
  return (
    <div data-testid="pdp-loading" className="grid gap-8 py-8 lg:grid-cols-2 lg:gap-14">
      <Skeleton className="aspect-[3/4] w-full" />
      <div className="space-y-4">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    </div>
  );
}

export default function ProductPage() {
  const { slug } = useParams();
  const { locale, t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();
  const {
    addToCart: addCartItem,
    cartMutationsBlocked,
    toggleWishlist,
    wishlistIds,
  } = useShop();
  const [selected, setSelected] = useState({});
  const [imageIndex, setImageIndex] = useState(0);
  const [quantity, setQuantity] = useState(1);

  const query = useQuery({
    queryKey: ["product", slug],
    queryFn: () => getProduct(slug),
    retry: false,
    refetchOnWindowFocus: true,
  });
  const product = query.data;
  const variants = useMemo(
    () =>
      (product?.variants || [])
        .filter((v) => v.is_active)
        .map((variant) => {
          const rawOptions =
            variant.option_values && typeof variant.option_values === "object" && !Array.isArray(variant.option_values)
              ? variant.option_values
              : {};
          const optionValues = Object.fromEntries(
            Object.entries(rawOptions)
              .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
              .map(([key, value]) => [
                key.trim().toLowerCase() === "size" ? "size" : key,
                String(value).trim(),
              ])
              .filter(([, value]) => value)
          );
          return { ...variant, option_values: optionValues };
        }),
    [product]
  );

  const dimensions = useMemo(() => {
    const dims = new Map();
    variants.forEach((v) =>
      Object.entries(v.option_values || {}).forEach(([key, value]) => {
        if (!dims.has(key)) dims.set(key, new Set());
        dims.get(key).add(value);
      })
    );
    return [...dims.entries()].map(([key, set]) => ({ key, values: [...set] }));
  }, [variants]);

  const requiresExplicitSizeChoice = Boolean(product?.size_selection_required);

  useEffect(() => {
    setSelected({});
    setImageIndex(0);
    setQuantity(1);
  }, [slug]);

  useEffect(() => {
    if (!variants.length || Object.keys(selected).length) return;
    const first = variants[0];
    const initialOptions = { ...first.option_values };
    if (requiresExplicitSizeChoice) delete initialOptions.size;
    setSelected(initialOptions);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variants, requiresExplicitSizeChoice]);

  useEffect(() => {
    if (product) {
      document.title = `${pickLocalized(product.translations, locale)} — MUSLIMAH CANTIK`;
    }
  }, [product, locale]);

  const isValueAvailable = (dimKey, value) =>
    variants.some(
      (v) =>
        v.option_values[dimKey] === value &&
        dimensions.every(
          (d) => d.key === dimKey || !selected[d.key] || v.option_values[d.key] === selected[d.key]
        )
    );

  const allSelected = dimensions.every((d) => selected[d.key]) &&
    (!requiresExplicitSizeChoice || Boolean(selected.size));
  const selectedVariant = allSelected
    ? variants.find((v) => dimensions.every((d) => v.option_values[d.key] === selected[d.key]))
    : null;

  const selectOption = (dimKey, value) => {
    setSelected((prev) => {
      const next = { ...prev, [dimKey]: value };
      const exact = variants.find((v) =>
        dimensions.every((d) => v.option_values[d.key] === next[d.key])
      );
      if (exact) return next;
      const fallback = variants.find((v) => v.option_values[dimKey] === value);
      if (!fallback) return next;
      const fallbackOptions = { ...fallback.option_values };
      if (requiresExplicitSizeChoice && dimKey !== "size") {
        const priorSizeVariant = prev.size && variants.find((variant) =>
          variant.option_values[dimKey] === value &&
          variant.option_values.size === prev.size &&
          dimensions.every((dimension) =>
            dimension.key === dimKey || dimension.key === "size" ||
            !prev[dimension.key] || variant.option_values[dimension.key] === prev[dimension.key]
          )
        );
        if (priorSizeVariant) return { ...priorSizeVariant.option_values };
        delete fallbackOptions.size;
      }
      return fallbackOptions;
    });
  };

  const images = useMemo(() => {
    const media = (product?.media || [])
      .slice()
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
      .map((m) => (typeof m === "string" ? m : m.url))
      .filter(Boolean);
    if (selectedVariant?.image_url) {
      return [selectedVariant.image_url, ...media.filter((u) => u !== selectedVariant.image_url)];
    }
    return media;
  }, [product, selectedVariant]);

  useEffect(() => {
    setImageIndex(0);
  }, [selectedVariant?.id]);

  useEffect(() => {
    setImageIndex((current) =>
      images.length ? Math.min(current, images.length - 1) : 0
    );
  }, [images.length]);

  if (query.isLoading) {
    return <div className="py-6 lg:py-10"><PdpSkeleton /></div>;
  }
  if (query.isError) {
    const notFound = query.error?.response?.status === 404;
    return (
      <div className="py-16" data-testid="pdp-error">
        {notFound ? (
          <EmptyState title={t("errors.notFound")} />
        ) : (
          <ErrorState message={t("errors.network")} onRetry={() => query.refetch()} />
        )}
      </div>
    );
  }

  const name = pickLocalized(product.translations, locale);
  const description = pickLocalized(product.translations, locale, "description");
  const attrs = product.attributes || {};
  const isSkincare = product.product_type === "skincare";
  const isBatik = product.product_type === "batik";
  const isParfum = product.product_type === "parfum";
  const hasSize = dimensions.some((d) => d.key === "size") &&
    (["apparel", "hijab"].includes(product.product_type) || isBatik);

  const unitPrice = selectedVariant
    ? selectedVariant.sale_price_override ??
      selectedVariant.price_override ??
      product.base_price
    : product.base_price;
  const compareAt = selectedVariant?.sale_price_override != null
    ? selectedVariant.price_override ?? product.base_price
    : product.compare_at_price;

  const maxQty = 99;
  const category = product.category;
  const department = category?.department;
  const ancestors = category?.ancestors || (department ? [department] : []);

  const addToCart = async () => {
    if (!selectedVariant) return;
    try {
      await addCartItem({
        product_id: product.id,
        variant_id: selectedVariant.id,
        quantity,
      });
      toast.success(t("cart.added"), {
        description: `${name} — ${selectedVariant.sku} × ${quantity}`,
      });
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.error === "quantity_limit") {
        toast.error(t("cart.quantityLimit", { count: d.maximum }));
      } else {
        toast.error(t("errors.generic"));
      }
    }
  };

  const wished = wishlistIds.has(product.id);
  const handleWishlist = async () => {
    try {
      const result = await toggleWishlist(product.id);
      if (result === "auth_required") {
        toast.info(t("wishlist.loginRequired"));
        navigate("/login", {
          state: {
            returnTo: `${location.pathname}${location.search}`,
            intent: { type: "wishlist_add", productId: product.id },
          },
        });
      } else {
        toast.success(t(result === "added" ? "wishlist.added" : "wishlist.removed"));
      }
    } catch {
      toast.error(t("errors.generic"));
    }
  };

  const infoSections = [
    description && { key: "description", title: t("pdp.description"), body: description },
    (attrs.fit || attrs.size_cm || attrs.includes || attrs.age_range || attrs.spf || attrs.motif || attrs.volume || attrs.format) && {
      key: "features",
      title: t("pdp.features"),
      list: [
        attrs.fit && `Fit: ${attrs.fit}`,
        attrs.size_cm && `Size: ${attrs.size_cm} cm`,
        attrs.includes && `Includes: ${attrs.includes}`,
        attrs.age_range && `Age: ${attrs.age_range} yrs`,
        attrs.spf && `SPF ${attrs.spf}`,
        attrs.motif && `${t("pdp.motif")}: ${attrs.motif}`,
        attrs.volume && `${t("options.volume")}: ${attrs.volume}`,
        attrs.format && `${t("options.format")}: ${attrs.format}`,
      ].filter(Boolean),
    },
    !isSkincare && (attrs.fabric || attrs.material || attrs.care) && {
      key: "materialCare",
      title: t("pdp.materialCare"),
      list: [attrs.fabric || attrs.material, attrs.care].filter(Boolean),
    },
    isSkincare && attrs.ingredients && {
      key: "ingredients",
      title: t("pdp.ingredients"),
      body: attrs.ingredients,
    },
    isSkincare && attrs.benefits && {
      key: "benefits",
      title: t("pdp.benefits"),
      body: attrs.benefits,
    },
    isSkincare && attrs.directions && {
      key: "directions",
      title: t("pdp.directions"),
      body: attrs.directions,
    },
    isParfum && (attrs.fragrance_family || attrs.notes || attrs.usage || attrs.alcohol_free) && {
      key: "fragrance",
      title: t("pdp.fragrance"),
      list: [
        attrs.fragrance_family && `${t("pdp.fragranceFamily")}: ${attrs.fragrance_family}`,
        attrs.notes && `${t("pdp.notes")}: ${attrs.notes}`,
        attrs.usage && `${t("pdp.usage")}: ${attrs.usage}`,
        attrs.alcohol_free && t("pdp.alcoholFree"),
      ].filter(Boolean),
    },
    {
      key: "details",
      title: t("pdp.details"),
      list: [
        `${t("pdp.sku")}: ${selectedVariant?.sku || "-"}`,
        `Brand: ${product.brand}`,
        category && `${pickLocalized(category.translations, locale)}`,
        isSkincare && attrs.skin_type && `${t("pdp.skinType")}: ${attrs.skin_type}`,
        isSkincare && attrs.halal_certified && t("pdp.halalCertified"),
      ].filter(Boolean),
    },
  ].filter(Boolean);

  return (
    <div data-testid="pdp-page" className="py-6 lg:py-10">
      <p data-testid="pdp-breadcrumb" className="text-xs text-muted-foreground">
        <Link to="/" className="hover:underline">{t("nav.home")}</Link>
        {ancestors.map((ancestor) => (
          <span key={ancestor.id}>
            {" / "}
            <Link
              to={ancestor.kind === "department"
                ? `/shop?department=${ancestor.slug}`
                : `/shop?category=${ancestor.slug}`}
              className="hover:underline"
            >
              {pickLocalized(ancestor.translations, locale)}
            </Link>
          </span>
        ))}
        {category ? (
          <>
            {" / "}
            <Link to={`/shop?category=${category.slug}`} className="hover:underline">
              {pickLocalized(category.translations, locale)}
            </Link>
          </>
        ) : null}
        {" / "}
        <span className="text-foreground">{name}</span>
      </p>

      <div className="mt-6 grid gap-8 lg:grid-cols-2 lg:gap-14">
        <div data-testid="pdp-gallery">
          <div className="overflow-hidden bg-secondary">
            <ImageWithFallback
              src={images[imageIndex]}
              alt={name}
              data-testid="pdp-main-image"
              className="aspect-[3/4] w-full object-cover"
            />
          </div>
          {images.length > 1 ? (
            <div
              data-testid="pdp-thumbnails"
              className="mt-3 flex gap-3 overflow-x-auto pb-1"
            >
              {images.map((url, i) => (
                <button
                  key={url + i}
                  type="button"
                  data-testid={`pdp-thumb-${i}`}
                  aria-label={`Image ${i + 1}`}
                  aria-pressed={imageIndex === i}
                  onClick={() => setImageIndex(i)}
                  className={`w-16 shrink-0 overflow-hidden border-2 sm:w-20 ${
                    imageIndex === i ? "border-foreground" : "border-transparent"
                  }`}
                >
                  <ImageWithFallback
                    src={url}
                    alt=""
                    loading="lazy"
                    className="aspect-[3/4] w-full object-cover"
                  />
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div data-testid="pdp-panel" className="lg:sticky lg:top-28 lg:self-start">
          <div className="flex items-center gap-2">
            <span data-testid="pdp-badge-preorder" className="bg-[#FDF7E9] px-2 py-0.5 text-[11px] font-semibold tracking-wide text-[#02422C]">
              {t("preorder.label")}
            </span>
            {product.new_arrival ? (
              <span data-testid="pdp-badge-new" className="bg-foreground px-2 py-0.5 text-[11px] font-semibold tracking-wide text-background">
                {t("product.new")}
              </span>
            ) : null}
            {compareAt ? (
              <span data-testid="pdp-badge-sale" className="bg-primary px-2 py-0.5 text-[11px] font-semibold tracking-wide text-primary-foreground">
                {t("product.sale")}
              </span>
            ) : null}
            {isSkincare && attrs.halal_certified ? (
              <span data-testid="pdp-badge-halal" className="border border-primary px-2 py-0.5 text-[11px] font-semibold tracking-wide text-primary">
                {t("pdp.halalCertified")}
              </span>
            ) : null}
          </div>
          <p className="mt-3 text-xs uppercase tracking-widest text-muted-foreground">
            {product.brand}
          </p>
          <h1 data-testid="pdp-title" className="mt-1 text-2xl font-semibold tracking-tight lg:text-3xl">
            {name}
          </h1>
          <p data-testid="pdp-preorder-notice" className="mt-2 text-sm leading-relaxed text-primary">
            {t("preorder.label")}
          </p>
          <p data-testid="pdp-size-availability" className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {t("preorder.sizeAvailability")}
          </p>
          <p data-testid="pdp-sku" className="mt-1 text-xs text-muted-foreground">
            {t("pdp.sku")}: {selectedVariant?.sku || "-"}
          </p>
          <div className="mt-3 text-lg">
            <PriceDisplay amount={unitPrice} compareAt={compareAt} />
          </div>

          {dimensions.map((dim) => (
            <div key={dim.key} className="mt-6" data-testid={`pdp-option-${dim.key}`}>
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-medium">
                  {t(`options.${dim.key}`)}
                  {selected[dim.key] ? (
                    <span className="ml-2 font-normal text-muted-foreground">
                      {selected[dim.key]}
                    </span>
                  ) : null}
                </p>
                {dim.key === "size" && hasSize ? <SizeGuide /> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                {dim.values.map((value) => {
                  const exists = variants.some((v) => v.option_values[dim.key] === value);
                  const comboAvailable = isValueAvailable(dim.key, value);
                  const isActive = selected[dim.key] === value;
                  return dim.key === "color" ? (
                    <button
                      key={value}
                      type="button"
                      data-testid={`pdp-color-${value.toLowerCase().replace(/\s+/g, "-")}`}
                      aria-label={`${t("options.color")}: ${value}`}
                      aria-pressed={isActive}
                      disabled={!exists}
                      onClick={() => selectOption(dim.key, value)}
                      className={`h-11 w-11 rounded-full border-2 transition-colors ${
                        isActive
                          ? "border-primary"
                          : exists
                            ? "border-border hover:border-foreground"
                            : "border-border opacity-30"
                        } ${exists && !comboAvailable ? "opacity-50" : ""}`}
                      style={{ backgroundColor: colorHex(value) }}
                    />
                  ) : (
                    <button
                      key={value}
                      type="button"
                      data-testid={`pdp-option-${dim.key}-${value.toLowerCase().replace(/\s+/g, "-")}`}
                      aria-pressed={isActive}
                      disabled={!exists}
                      onClick={() => selectOption(dim.key, value)}
                      className={`min-h-11 border px-4 py-2 text-sm font-medium transition-colors ${
                        isActive
                          ? "border-primary bg-primary text-primary-foreground"
                          : exists
                            ? "border-border hover:border-foreground"
                            : "border-border text-muted-foreground opacity-40 line-through"
                      } ${exists && !comboAvailable && !isActive ? "opacity-50" : ""}`}
                    >
                      {value}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          <div className="mt-5 flex items-center gap-4">
            <div className="flex items-center border border-border" data-testid="pdp-quantity">
              <button
                type="button"
                data-testid="pdp-qty-minus"
                aria-label="Decrease quantity"
                disabled={quantity <= 1}
                onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                className="inline-flex h-10 w-10 items-center justify-center disabled:opacity-30"
              >
                <Minus className="h-4 w-4" aria-hidden="true" />
              </button>
              <span data-testid="pdp-qty-value" className="w-10 text-center text-sm font-medium">
                {quantity}
              </span>
              <button
                type="button"
                data-testid="pdp-qty-plus"
                aria-label="Increase quantity"
                disabled={quantity >= maxQty}
                onClick={() => setQuantity((q) => Math.min(maxQty, q + 1))}
                className="inline-flex h-10 w-10 items-center justify-center disabled:opacity-30"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <p className="text-xs text-muted-foreground">{t("pdp.quantity")}</p>
          </div>

          <div className="mt-6 flex gap-3">
            <button
              type="button"
              data-testid="pdp-add-to-cart"
              disabled={!selectedVariant || cartMutationsBlocked}
              onClick={addToCart}
              className="flex h-12 flex-1 items-center justify-center gap-2 bg-foreground text-sm font-semibold text-background transition-colors hover:bg-primary disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ShoppingBag className="h-4 w-4" aria-hidden="true" />
              {t("pdp.addToCart")}
            </button>
            <button
              type="button"
              data-testid="pdp-add-to-wishlist"
              aria-label={t("pdp.addToWishlist")}
              aria-pressed={wished}
              onClick={handleWishlist}
              className={`inline-flex h-12 w-12 items-center justify-center border transition-colors hover:border-primary hover:text-primary ${
                wished ? "border-primary text-primary" : "border-border text-foreground"
              }`}
            >
              <Heart className="h-5 w-5" fill={wished ? "currentColor" : "none"} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      <div className="mt-10 lg:mt-14" data-testid="pdp-sections">
        <Accordion type="multiple" defaultValue={["description"]} className="w-full">
          {infoSections.map((section) => (
            <AccordionItem key={section.key} value={section.key} data-testid={`pdp-section-${section.key}`}>
              <AccordionTrigger className="text-sm font-semibold">
                {section.title}
              </AccordionTrigger>
              <AccordionContent>
                {section.body ? (
                  <p className="text-sm text-muted-foreground">{section.body}</p>
                ) : (
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {section.list.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                )}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </div>
  );
}
