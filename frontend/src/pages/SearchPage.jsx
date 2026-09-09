import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getProducts } from "@/lib/api";
import { toCardProduct } from "@/lib/localize";
import ProductGrid from "@/components/common/ProductGrid";
import EmptyState from "@/components/common/EmptyState";
import ErrorState from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";

export default function SearchPage() {
  const { locale, t } = useI18n();
  const [searchParams] = useSearchParams();
  const q = (searchParams.get("q") || "").trim();
  const page = Number(searchParams.get("page")) || 1;

  const productsQuery = useQuery({
    queryKey: ["search", q, page],
    queryFn: () => getProducts({ q, page, limit: 12 }),
    enabled: Boolean(q),
  });

  const data = productsQuery.data;
  const products = (data?.items || []).map((p) => toCardProduct(p, locale));

  return (
    <div data-testid="search-page" className="py-6 lg:py-10">
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("search.resultsFor", { q })}
      </h1>
      <p data-testid="search-results-count" className="mt-2 text-sm text-muted-foreground">
        {data ? t("search.resultsCount", { count: data.total }) : t("common.loading")}
      </p>
      <div className="mt-8">
        {!q ? (
          <EmptyState title={t("common.empty")} />
        ) : productsQuery.isLoading ? (
          <div data-testid="search-loading" className="grid grid-cols-2 gap-x-3 gap-y-8 md:grid-cols-3 lg:grid-cols-4 lg:gap-x-5">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i}>
                <Skeleton className="aspect-[3/4] w-full" />
                <Skeleton className="mt-3 h-4 w-3/4" />
              </div>
            ))}
          </div>
        ) : productsQuery.isError ? (
          <ErrorState message={t("errors.network")} onRetry={() => productsQuery.refetch()} />
        ) : products.length === 0 ? (
          <EmptyState
            title={t("search.noResults")}
            description={t("common.empty")}
          />
        ) : (
          <ProductGrid products={products} testId="search-results-grid" />
        )}
      </div>
    </div>
  );
}
