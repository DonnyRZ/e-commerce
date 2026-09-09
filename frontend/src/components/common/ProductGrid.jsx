import ProductCard from "./ProductCard";

export default function ProductGrid({ products, testId = "product-grid" }) {
  return (
    <div
      data-testid={testId}
      className="grid grid-cols-2 gap-x-3 gap-y-8 sm:gap-x-4 md:grid-cols-3 lg:grid-cols-4 lg:gap-x-5 lg:gap-y-10"
    >
      {products.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}
    </div>
  );
}
