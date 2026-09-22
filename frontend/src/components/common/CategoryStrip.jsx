import CategoryCard from "./CategoryCard";

export default function CategoryStrip({ categories, nameOf, linkFor, testIdPrefix }) {
  return (
    <div
      data-testid="category-strip"
      className="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 [scrollbar-width:thin] lg:gap-5"
    >
      {categories.map((c) => (
        <div key={c.id || c.slug} className="w-36 shrink-0 snap-start sm:w-44 lg:w-48">
          <CategoryCard
            category={c}
            name={nameOf(c)}
            href={linkFor ? linkFor(c) : undefined}
            testIdPrefix={testIdPrefix}
          />
        </div>
      ))}
    </div>
  );
}
