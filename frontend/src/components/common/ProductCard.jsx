import { Link, useNavigate } from "react-router-dom";
import { Heart } from "lucide-react";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { useShop } from "@/lib/ShopContext";
import PriceDisplay from "./PriceDisplay";
import ImageWithFallback from "./ImageWithFallback";

export default function ProductCard({ product }) {
  const { t } = useI18n();
  const { toggleWishlist, wishlistIds } = useShop();
  const navigate = useNavigate();
  const href = product.href || "/shop";
  const wished = wishlistIds.has(product.id);

  const handleWishlist = async () => {
    const result = await toggleWishlist(product.id);
    if (result === "auth_required") {
      toast.info(t("wishlist.loginRequired"));
      navigate("/login");
    } else if (result === "added") {
      toast.success(t("wishlist.added"));
    } else if (result === "removed") {
      toast.success(t("wishlist.removed"));
    }
  };
  return (
    <article data-testid={`product-card-${product.slug || product.id}`} className="group">
      <div className="relative overflow-hidden bg-secondary">
        <Link to={href} aria-label={product.name}>
          <ImageWithFallback
            src={product.image}
            alt={product.name}
            loading="lazy"
            className="aspect-[3/4] w-full object-cover"
          />
        </Link>
        <div className="absolute left-2 top-2 flex flex-wrap gap-1">
          {product.isDemo ? (
            <span
              data-testid={`badge-preview-${product.slug || product.id}`}
              className="bg-[#FDF7E9] px-2 py-0.5 text-[11px] font-semibold tracking-wide text-[#02422C] shadow-sm"
            >
              {t("product.preview")}
            </span>
          ) : null}
          {product.badge ? (
            <span
              data-testid={`badge-${product.badge}-${product.slug || product.id}`}
              className={`px-2 py-0.5 text-[11px] font-semibold tracking-wide ${
                product.badge === "sale"
                  ? "bg-primary text-primary-foreground"
                  : "bg-foreground text-background"
              }`}
            >
              {t(`product.${product.badge}`)}
            </span>
          ) : null}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5" data-testid={`swatches-${product.slug || product.id}`}>
          {product.colors.map((color) => (
            <span
              key={color}
              className="h-3.5 w-3.5 rounded-full border border-border"
              style={{ backgroundColor: color }}
            />
          ))}
        </div>
        <button
          type="button"
          data-testid={`wishlist-${product.slug || product.id}`}
          aria-label={t("product.wishlist")}
          aria-pressed={wished}
          onClick={handleWishlist}
          className={`inline-flex h-8 w-8 items-center justify-center transition-colors hover:text-primary ${
            wished ? "text-primary" : "text-foreground"
          }`}
        >
          <Heart
            className="h-[18px] w-[18px]"
            fill={wished ? "currentColor" : "none"}
            aria-hidden="true"
          />
        </button>
      </div>
      <p className="mt-1 text-[11px] uppercase tracking-wide text-muted-foreground">
        {product.meta}
      </p>
      {product.isDemo ? (
        <p data-testid={`preview-label-${product.slug || product.id}`} className="mt-0.5 text-[11px] text-primary">
          {t("product.previewLabel")}
        </p>
      ) : null}
      <h3 className="mt-0.5 text-sm font-medium leading-snug">
        <Link to={href} className="hover:underline">
          {product.name}
        </Link>
      </h3>
      <PriceDisplay
        amount={product.price}
        compareAt={product.compareAt}
        className="mt-1"
      />
      {!product.isDemo && product.stockState === "out_of_stock" ? (
        <p
          data-testid={`stock-out-${product.slug || product.id}`}
          className="mt-1 text-xs font-medium text-destructive"
        >
          {t("product.outOfStock")}
        </p>
      ) : !product.isDemo && product.stockState === "low_stock" ? (
        <p
          data-testid={`stock-low-${product.slug || product.id}`}
          className="mt-1 text-xs font-medium text-primary"
        >
          {t("product.lowStock")}
        </p>
      ) : null}
    </article>
  );
}
