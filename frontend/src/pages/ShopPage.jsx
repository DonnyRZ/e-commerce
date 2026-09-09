import { ArrowUpDown, SlidersHorizontal } from "lucide-react";
import { useI18n } from "@/i18n";
import { CATEGORIES, DEMO_PRODUCTS, localizedName } from "@/data/demo";
import CategoryStrip from "@/components/common/CategoryStrip";
import ProductGrid from "@/components/common/ProductGrid";

export default function ShopPage() {
  const { locale, t } = useI18n();
  const nameOf = (obj) => localizedName(obj, locale);

  return (
    <div data-testid="shop-page" className="py-6 lg:py-10">
      <p data-testid="plp-breadcrumb" className="text-xs text-muted-foreground">
        {t("nav.home")} / {t("page.title.shop")}
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("page.title.shop")}
      </h1>
      <div className="mt-4 flex items-center justify-between border-y border-border py-3">
        <p data-testid="plp-results" className="text-sm">
          {t("plp.results", { count: DEMO_PRODUCTS.length })}
        </p>
        <div className="flex items-center gap-5">
          <button
            type="button"
            data-testid="plp-sort"
            className="flex items-center gap-1.5 text-sm font-medium text-foreground hover:text-primary"
          >
            <ArrowUpDown className="h-4 w-4" aria-hidden="true" />
            {t("plp.sortBy")}
          </button>
          <button
            type="button"
            data-testid="plp-filter"
            className="flex items-center gap-1.5 text-sm font-medium text-foreground hover:text-primary"
          >
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            {t("plp.filter")}
          </button>
        </div>
      </div>
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold">{t("home.shopByCategory")}</h2>
        <CategoryStrip categories={CATEGORIES.slice(0, 10)} nameOf={nameOf} />
      </div>
      <div className="mt-10">
        <ProductGrid products={DEMO_PRODUCTS} />
      </div>
    </div>
  );
}
