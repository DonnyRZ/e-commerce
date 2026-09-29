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
        /> : <div aria-hidden="true" className="h-full w-full bg-neutral-50" />}
      </div>
      <p className="mt-2 text-sm font-medium leading-snug group-hover:underline">
        {name}
      </p>
    </Link>
  );
}
