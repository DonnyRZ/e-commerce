import { Link } from "react-router-dom";

export default function CategoryCard({ category, name, onNavigate }) {
  return (
    <Link
      to={`/shop?category=${category.slug}`}
      onClick={onNavigate}
      data-testid={`category-card-${category.slug}`}
      className="group block"
    >
      <div className="overflow-hidden bg-secondary">
        <img
          src={category.image}
          alt={name}
          loading="lazy"
          className="aspect-[3/4] w-full object-cover transition-transform duration-300 group-hover:scale-105"
        />
      </div>
      <p className="mt-2 text-sm font-medium leading-snug group-hover:underline">
        {name}
      </p>
    </Link>
  );
}
