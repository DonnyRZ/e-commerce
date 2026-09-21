import { Link } from "react-router-dom";
import ImageWithFallback from "./ImageWithFallback";

export default function CategoryCard({ category, name, onNavigate, href, testIdPrefix = "category-card" }) {
  return (
    <Link
      to={href || `/shop?category=${category.slug}`}
      onClick={onNavigate}
      data-testid={`${testIdPrefix}-${category.slug}`}
      className="group block"
    >
      <div className="flex aspect-[3/4] items-center justify-center overflow-hidden bg-white p-4">
        <ImageWithFallback
          src={category.image}
          alt={name}
          loading="lazy"
          className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
        />
      </div>
      <p className="mt-2 text-sm font-medium leading-snug group-hover:underline">
        {name}
      </p>
    </Link>
  );
}
