import { useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import ProductCard from "./ProductCard";

export default function ProductRail({ products, testId = "product-rail" }) {
  const railRef = useRef(null);
  if (!products?.length) return null;

  const scroll = (direction) => {
    railRef.current?.scrollBy({
      left: direction * Math.max(railRef.current.clientWidth * 0.82, 280),
      behavior: "smooth",
    });
  };

  return (
    <div className="relative" data-testid={testId}>
      <div className="mb-3 flex justify-end gap-2">
        <button type="button" aria-label="Geser pilihan ke kiri" onClick={() => scroll(-1)} className="inline-flex h-9 w-9 items-center justify-center border border-border bg-background text-foreground transition hover:border-primary hover:text-primary" data-testid={`${testId}-previous`}>
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        <button type="button" aria-label="Geser pilihan ke kanan" onClick={() => scroll(1)} className="inline-flex h-9 w-9 items-center justify-center border border-border bg-background text-foreground transition hover:border-primary hover:text-primary" data-testid={`${testId}-next`}>
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div ref={railRef} className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-3 [scrollbar-width:thin] sm:gap-4 lg:gap-5">
        {products.map((product) => (
          <div key={product.id} className="w-[calc((100%-12px)/2)] shrink-0 snap-start sm:w-[calc((100%-32px)/3)] lg:w-[calc((100%-60px)/4)]">
            <ProductCard product={product} />
          </div>
        ))}
      </div>
    </div>
  );
}
