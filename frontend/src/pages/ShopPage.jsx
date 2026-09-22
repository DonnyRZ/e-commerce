import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpDown, ChevronLeft, ChevronRight, SlidersHorizontal } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import {
  getCategory,
  getCatalogTree,
  getFilters,
  getProducts,
} from "@/lib/api";
import { pickLocalized, toCardCategory, toCardProduct } from "@/lib/localize";
import { CATEGORY_VISUALS } from "@/lib/catalogVisuals";
import { findTaxonomyNode, leafTaxonomy } from "@/lib/taxonomy";
import CategoryStrip from "@/components/common/CategoryStrip";
import ProductGrid from "@/components/common/ProductGrid";
import EmptyState from "@/components/common/EmptyState";
import ErrorState from "@/components/common/ErrorState";
import FilterPanel from "@/components/plp/FilterPanel";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const PAGE_SIZE = 12;
const SORT_OPTIONS = ["featured", "newest", "price_asc", "price_desc"];
const BADGE_TITLES = {
  new: "nav.newArrivals",
  bestseller: "nav.bestSellers",
  sale: "nav.sale",
};

function GridSkeleton() {
  return (
    <div data-testid="plp-loading" className="grid grid-cols-2 gap-x-3 gap-y-8 md:grid-cols-3 lg:grid-cols-4 lg:gap-x-5">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i}>
          <Skeleton className="aspect-[3/4] w-full" />
          <Skeleton className="mt-3 h-4 w-3/4" />
          <Skeleton className="mt-2 h-4 w-1/3" />
        </div>
      ))}
    </div>
  );
}

export default function ShopPage() {
  const { locale, t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const params = Object.fromEntries(searchParams.entries());
  const { department, category, badge } = params;
  const page = Number(params.page) || 1;

  const setParam = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (value === undefined || value === null || value === "") next.delete(key);
    else next.set(key, String(value));
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };
  const clearFilters = () => {
    const next = new URLSearchParams(searchParams);
    ["min_price", "max_price", "color", "size", "volume", "motif", "format", "page"].forEach((k) =>
      next.delete(k)
    );
    setSearchParams(next);
  };

  const { data: catalogTree = [] } = useQuery({
    queryKey: ["catalog-tree"],
    queryFn: getCatalogTree,
    staleTime: 5 * 60 * 1000,
  });
  const { data: categoryDetail } = useQuery({
    queryKey: ["category", category],
    queryFn: () => getCategory(category),
    enabled: Boolean(category),
  });
  const { data: filtersMeta } = useQuery({
    queryKey: ["filters", department || "", category || ""],
    queryFn: () => getFilters({ department, category }),
  });
  const productsQuery = useQuery({
    queryKey: ["products", searchParams.toString()],
    queryFn: () =>
      getProducts({
        department,
        category,
        badge,
        q: params.q,
        sort: params.sort || "featured",
        page,
        limit: PAGE_SIZE,
        min_price: params.min_price,
        max_price: params.max_price,
        color: params.color,
        size: params.size,
        volume: params.volume,
        motif: params.motif,
        format: params.format,
      }),
    placeholderData: (prev) => prev,
  });

  const activeDept = catalogTree.find((d) => d.slug === department);
  const activeNode = category
    ? categoryDetail
    : activeDept || findTaxonomyNode(catalogTree, department);
  const title = categoryDetail
    ? pickLocalized(categoryDetail.translations, locale)
    : activeDept
      ? pickLocalized(activeDept.translations, locale)
      : badge && BADGE_TITLES[badge]
        ? t(BADGE_TITLES[badge])
        : t("page.title.shop");

  // Every department exposes one flat category strip. Products are assigned
  // directly to these categories.
  const stripNodes = activeNode?.kind === "department"
    ? leafTaxonomy([activeNode])
    : activeNode?.children?.length
    ? activeNode.children
    : categoryDetail
      ? []
      : catalogTree.flatMap((node) => node.children || []);
  const stripCategories = stripNodes
    .map((c) => ({
      ...toCardCategory(c, locale),
      image: CATEGORY_VISUALS[c.slug] || "",
      comingSoon: !CATEGORY_VISUALS[c.slug],
      comingSoonLabel: locale === "id" ? "Segera hadir" : locale === "uz" ? "Tez orada" : locale === "ru" ? "Скоро" : "Coming soon",
    }));

  const breadcrumbNodes = categoryDetail?.ancestors || (activeDept ? [activeDept] : []);

  const data = productsQuery.data;
  const products = (data?.items || []).map((p) => toCardProduct(p, locale));
  const hasActiveFilters = [
    "q", "badge", "min_price", "max_price", "color", "size", "volume", "motif", "format",
  ].some((key) => params[key]);

  return (
    <div data-testid="shop-page" className="py-6 lg:py-10">
      <p data-testid="plp-breadcrumb" className="text-xs text-muted-foreground">
        <Link to="/" className="hover:underline">{t("nav.home")}</Link>
        {" / "}
        {breadcrumbNodes.map((node) => (
          <span key={node.id}>
            <Link
              to={node.kind === "department"
                ? `/shop?department=${node.slug}`
                : `/shop?category=${node.slug}`}
              className="hover:underline"
            >
              {pickLocalized(node.translations, locale)}
            </Link>
            {" / "}
          </span>
        ))}
        <span className="text-foreground">{title}</span>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight lg:text-3xl">{title}</h1>

      <div className="mt-4 flex items-center justify-between border-y border-border py-3">
        <p data-testid="plp-results" className="text-sm">
          {data ? t("plp.results", { count: data.total }) : t("common.loading")}
        </p>
        <div className="flex items-center gap-4">
          <label className="hidden items-center gap-2 text-sm sm:flex">
            <ArrowUpDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <select
              data-testid="plp-sort"
              value={params.sort || "featured"}
              onChange={(e) => setParam("sort", e.target.value)}
              className="cursor-pointer bg-transparent text-sm font-medium outline-none"
            >
              {SORT_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {t(`sort.${s === "price_asc" ? "priceAsc" : s === "price_desc" ? "priceDesc" : s}`)}
                </option>
              ))}
            </select>
          </label>
          <Sheet>
            <SheetTrigger asChild>
              <button
                type="button"
                data-testid="plp-filter"
                className="flex items-center gap-1.5 text-sm font-medium text-foreground hover:text-primary lg:hidden"
              >
                <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
                {t("plp.filter")}
              </button>
            </SheetTrigger>
            <SheetContent side="left" className="w-80 overflow-y-auto p-6" data-testid="filter-sheet">
              <SheetTitle className="sr-only">{t("plp.filters")}</SheetTitle>
              <FilterPanel
                meta={filtersMeta}
                params={params}
                setParam={setParam}
                clearAll={clearFilters}
              />
            </SheetContent>
          </Sheet>
        </div>
      </div>

      {stripCategories.length ? (
        <div className="mt-8">
          <CategoryStrip categories={stripCategories} nameOf={(c) => c.name} />
        </div>
      ) : null}

      <div className="mt-10 lg:grid lg:grid-cols-[240px_1fr] lg:gap-10">
        <aside className="hidden lg:block" data-testid="filter-sidebar">
          <FilterPanel
            meta={filtersMeta}
            params={params}
            setParam={setParam}
            clearAll={clearFilters}
          />
        </aside>
        <div>
          {productsQuery.isLoading ? (
            <GridSkeleton />
          ) : productsQuery.isError ? (
            <ErrorState onRetry={() => productsQuery.refetch()} />
          ) : products.length === 0 ? (
            <EmptyState
              title={t(hasActiveFilters ? "plp.noResults" : "plp.noProducts")}
              description={t(hasActiveFilters ? "plp.noResultsHint" : "plp.noProductsHint")}
            />
          ) : (
            <>
              <ProductGrid products={products} />
              {data && data.pages > 1 ? (
                <nav
                  data-testid="plp-pagination"
                  aria-label="Pagination"
                  className="mt-12 flex items-center justify-center gap-4"
                >
                  <Button
                    variant="outline"
                    size="sm"
                    data-testid="plp-prev-page"
                    disabled={page <= 1}
                    onClick={() => setParam("page", page - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                    {t("plp.prev")}
                  </Button>
                  <span data-testid="plp-page-indicator" className="text-sm text-muted-foreground">
                    {t("plp.pageOf", { page: data.page, pages: data.pages })}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    data-testid="plp-next-page"
                    disabled={page >= data.pages}
                    onClick={() => setParam("page", page + 1)}
                  >
                    {t("plp.next")}
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </nav>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
