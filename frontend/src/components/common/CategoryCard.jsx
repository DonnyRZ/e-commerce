import { Link } from "react-router-dom";
import { ShoppingBag } from "lucide-react";
import ImageWithFallback from "./ImageWithFallback";

export default function CategoryCard({ category, name, onNavigate, href, testIdPrefix = "category-card", variant = "default" }) {
  const hasImage = typeof category.image === "string"
    && category.image.trim()
    && !category.image.includes("image-placeholder");
  const frameClassName = variant === "wide" ? "aspect-[4/3]" : "aspect-[3/4]";

  return (
    <Link
      to={href || `/shop?category=${category.slug}`}
      onClick={onNavigate}
      data-testid={`${testIdPrefix}-${category.slug}`}
      className="group block"
    >
      <div className={`flex ${frameClassName} items-center justify-center overflow-hidden bg-brand-ivory p-2 sm:p-3`}>
        {hasImage ? <ImageWithFallback
          src={category.image}
          alt={name}
          loading="lazy"
          className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
        /> : <div className="flex h-full w-full items-center justify-center border border-brand-green/10 bg-white/45 text-brand-green/55">
          <ShoppingBag className="h-10 w-10 stroke-[1.25] sm:h-12 sm:w-12" aria-hidden="true" />
        </div>}
      </div>
      <p className="mt-2 text-sm font-medium leading-snug group-hover:underline">
        {name}
      </p>
    </Link>
  );
}
