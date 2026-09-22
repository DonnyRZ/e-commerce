import CategoryCard from "./CategoryCard";

export default function CategoryStrip({ categories, nameOf, linkFor, testIdPrefix, fillDesktop = false, cardVariant = "default" }) {
  return (
    <div
      data-testid="category-strip"
      className={fillDesktop
        ? "flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 [scrollbar-width:thin] lg:grid lg:grid-cols-6 lg:gap-6 lg:overflow-visible lg:pb-0"
        : "flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 [scrollbar-width:thin] lg:gap-5"}
    >
      {categories.map((c) => (
        <div key={c.id || c.slug} className={fillDesktop ? "w-36 shrink-0 snap-start sm:w-44 lg:w-auto lg:min-w-0" : "w-36 shrink-0 snap-start sm:w-44 lg:w-48"}>
          <CategoryCard
            category={c}
            name={nameOf(c)}
            href={linkFor ? linkFor(c) : undefined}
            testIdPrefix={testIdPrefix}
            variant={cardVariant}
          />
        </div>
      ))}
    </div>
  );
}
