import { Link, Navigate, useLocation } from "react-router-dom";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { useShop } from "@/lib/ShopContext";
import { pickLocalized } from "@/lib/localize";
import EmptyState from "@/components/common/EmptyState";
import ProductCard from "@/components/common/ProductCard";
import { Skeleton } from "@/components/ui/skeleton";

export default function WishlistPage() {
  const { t, locale } = useI18n();
  const { user, checking } = useAuth();
  const { wishlist } = useShop();
  const location = useLocation();

  if (checking) {
    return (
      <div className="py-8" data-testid="wishlist-loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 aspect-[3/4] w-full max-w-xs" />
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

  const items = wishlist?.items || [];
  const cards = items.map((i) => ({
    id: i.product_id,
    slug: i.slug,
    name: pickLocalized(i.translations, locale),
    image: i.image_url || "",
    price: i.base_price,
    compareAt: i.compare_at_price,
    colors: [],
    meta: (i.brand || "").toUpperCase(),
    badge: i.compare_at_price ? "sale" : null,
    stockState: i.stock_state,
    href: `/product/${i.slug}`,
  }));

  return (
    <div data-testid="wishlist-page" className="py-8 lg:py-12">
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("wishlist.title")}
      </h1>
      {items.length === 0 ? (
        <div data-testid="wishlist-empty">
          <EmptyState
            title={t("wishlist.empty")}
            description={t("wishlist.emptyHint")}
            action={
              <Link
                to="/shop"
                data-testid="wishlist-empty-cta"
                className="inline-flex h-11 items-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
              >
                {t("cart.emptyCta")}
              </Link>
            }
          />
        </div>
      ) : (
        <div
          data-testid="wishlist-grid"
          className="mt-8 grid grid-cols-2 gap-x-3 gap-y-8 sm:gap-x-4 md:grid-cols-3 lg:grid-cols-4 lg:gap-x-5 lg:gap-y-10"
        >
          {cards.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </div>
  );
}
