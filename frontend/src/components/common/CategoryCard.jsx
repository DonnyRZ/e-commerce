import { Link } from "react-router-dom";
import ImageWithFallback from "./ImageWithFallback";

export default function CategoryCard({ category, name, onNavigate, href, testIdPrefix = "category-card", variant = "default" }) {
  const hasImage = typeof category.image === "string"
    && category.image.trim()
    && !category.image.includes("image-placeholder");
  const frameClassName = variant === "portrait" ? "aspect-[3/4]" : "aspect-square";

  return (
    <Link
      to={href || `/shop?category=${category.slug}`}
      onClick={onNavigate}
      data-testid={`${testIdPrefix}-${category.slug}`}
      className="group block"
    >
      <div className={`relative flex ${frameClassName} items-center justify-center overflow-hidden bg-white`}>
        {hasImage ? <ImageWithFallback
          src={category.image}
          alt={name}
          loading="lazy"
          className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
        /> : <div className="flex h-full w-full items-center justify-center bg-white px-4 text-center">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{category.comingSoonLabel || "Coming soon"}</span>
        </div>}
        {category.comingSoon ? <span className="absolute inset-x-0 bottom-0 bg-white/92 px-2 py-2 text-center text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{category.comingSoonLabel || "Coming soon"}</span> : null}
      </div>
      <p className="mt-2 text-sm font-medium leading-snug group-hover:underline">
        {name}
      </p>
    </Link>
  );
}
