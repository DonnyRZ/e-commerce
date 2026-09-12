import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCatalogTree, getCmsBundle, getProducts } from "@/lib/api";
import { mediaUrl, pickLocalized, toCardCategory, toCardProduct } from "@/lib/localize";
import { HERO_IMAGE } from "@/data/demo";
import { leafTaxonomy } from "@/lib/taxonomy";
import CategoryStrip from "@/components/common/CategoryStrip";
import EditorialSection from "@/components/common/EditorialSection";
import ProductGrid from "@/components/common/ProductGrid";
import ErrorState from "@/components/common/ErrorState";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";

function GridSkeleton({ testId }) {
  return (
    <div data-testid={testId} className="grid grid-cols-2 gap-x-3 gap-y-8 md:grid-cols-3 lg:grid-cols-4 lg:gap-x-5">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i}>
          <Skeleton className="aspect-[3/4] w-full" />
          <Skeleton className="mt-3 h-4 w-3/4" />
        </div>
      ))}
    </div>
  );
}

export default function HomePage() {
  const { locale, t } = useI18n();

  const catalogQuery = useQuery({
    queryKey: ["catalog-tree"],
    queryFn: getCatalogTree,
    staleTime: 5 * 60 * 1000,
  });
  const catalogTree = catalogQuery.data || [];
  const departments = catalogTree;
  const newArrivals = useQuery({
    queryKey: ["products", "home-new"],
    queryFn: () => getProducts({ badge: "new", limit: 8 }),
  });
  const bestSellers = useQuery({
    queryKey: ["products", "home-best"],
    queryFn: () => getProducts({ badge: "bestseller", limit: 8 }),
  });
  const cmsBundleQuery = useQuery({
    queryKey: ["cms", "bundle"],
    queryFn: getCmsBundle,
    staleTime: 60_000,
  });
  const cmsBundle = cmsBundleQuery.data;

  const hero = cmsBundle?.hero;
  const heroImage = mediaUrl(hero?.image_url) || HERO_IMAGE;
  const heroEyebrow = pickLocalized(hero?.translations, locale, "eyebrow") || t("brand.tagline");
  const heroTitle = pickLocalized(hero?.translations, locale) || t("page.home.heroTitle");
  const heroAlt = pickLocalized(hero?.translations, locale, "alt_text") || heroTitle;
  const heroSubtitle = pickLocalized(hero?.translations, locale, "subtitle") || t("page.home.heroSubtitle");
  const heroPrimary = {
    label: pickLocalized(hero?.translations, locale, "cta_label") || t("home.shopNow"),
    to: hero?.cta_url || "/shop",
  };
  const heroSecondary = {
    label: pickLocalized(hero?.translations, locale, "secondary_cta_label") || t("home.allDepartments"),
    to: hero?.secondary_cta_url || "/shop",
  };

  const stripCategories = leafTaxonomy(catalogTree)
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order)
    .slice(0, 8)
    .map((c) => toCardCategory(c, locale));

  return (
    <div data-testid="home-page">
      <section data-testid="home-hero" className="relative -mx-4 sm:-mx-6 lg:-mx-10">
        <ImageWithFallback
          src={heroImage}
          alt={heroAlt}
          className="h-[60vh] w-full object-cover lg:h-[72vh]"
        />
        <div className="absolute inset-x-0 bottom-0 pb-8 pt-24 text-center text-white [background:linear-gradient(to_top,rgba(0,0,0,0.55),transparent)] lg:pb-12">
          <p className="text-[11px] font-medium uppercase tracking-[0.2em] sm:text-xs">
            {heroEyebrow}
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">
            {heroTitle}
          </h1>
          <p className="mx-auto mt-2 max-w-xl px-4 text-sm text-white/85">
            {heroSubtitle}
          </p>
          <div className="mt-5 flex items-center justify-center gap-3">
            <Link
              to={heroPrimary.to}
              data-testid="hero-cta-shop"
              className="rounded-full bg-background px-6 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
            >
              {heroPrimary.label}
            </Link>
            <Link
              to={heroSecondary.to}
              data-testid="hero-cta-departments"
              className="rounded-full border border-white/70 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/10"
            >
              {heroSecondary.label}
            </Link>
          </div>
        </div>
      </section>

      <section data-testid="home-categories" className="py-10 lg:py-14">
        <h2 className="mb-5 text-lg font-semibold lg:text-xl">
          {t("home.shopByCategory")}
        </h2>
        {catalogQuery.isError ? (
          <ErrorState onRetry={() => catalogQuery.refetch()} />
        ) : stripCategories.length ? (
          <CategoryStrip categories={stripCategories} nameOf={(c) => c.name} />
        ) : (
          <div className="flex gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[3/4] w-36 shrink-0 sm:w-44 lg:w-48" />
            ))}
          </div>
        )}
      </section>

      <section data-testid="home-new-arrivals" className="py-4 lg:py-6">
        <div className="mb-5 flex items-end justify-between">
          <h2 className="text-lg font-semibold lg:text-xl">{t("home.newArrivals")}</h2>
          <Link
            to="/shop?badge=new"
            data-testid="new-arrivals-view-all"
            className="text-sm font-medium text-foreground underline-offset-4 hover:underline"
          >
            {t("home.viewAll")}
          </Link>
        </div>
        {newArrivals.isError ? (
          <ErrorState onRetry={() => newArrivals.refetch()} />
        ) : newArrivals.isLoading ? (
          <GridSkeleton testId="new-arrivals-loading" />
        ) : (
          <ProductGrid
            products={(newArrivals.data?.items || []).map((p) => toCardProduct(p, locale))}
            testId="new-arrivals-grid"
          />
        )}
      </section>

      <section data-testid="home-departments" className="py-10 lg:py-14">
        <div className="grid gap-4 sm:grid-cols-3 lg:gap-5">
          {departments.map((dept) => (
            <Link
              key={dept.id}
              to={`/shop?department=${dept.slug}`}
              data-testid={`department-tile-${dept.slug}`}
              className="group relative block overflow-hidden bg-secondary"
            >
              <ImageWithFallback
                src={dept.image_url}
                alt={pickLocalized(dept.translations, locale)}
                loading="lazy"
                className="aspect-[4/5] w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
              <div className="absolute inset-x-0 bottom-0 flex items-center justify-between p-4 text-white [background:linear-gradient(to_top,rgba(0,0,0,0.55),transparent)]">
                <span className="text-sm font-semibold">
                  {pickLocalized(dept.translations, locale)}
                </span>
                <span className="text-xs underline underline-offset-4">
                  {t("home.deptCta")}
                </span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section data-testid="home-best-sellers" className="pb-12 pt-2 lg:pb-16">
        <div className="mb-5 flex items-end justify-between">
          <h2 className="text-lg font-semibold lg:text-xl">{t("home.bestSellers")}</h2>
          <Link
            to="/shop?badge=bestseller"
            data-testid="best-sellers-view-all"
            className="text-sm font-medium text-foreground underline-offset-4 hover:underline"
          >
            {t("home.viewAll")}
          </Link>
        </div>
        {bestSellers.isError ? (
          <ErrorState onRetry={() => bestSellers.refetch()} />
        ) : bestSellers.isLoading ? (
          <GridSkeleton testId="best-sellers-loading" />
        ) : (
          <ProductGrid
            products={(bestSellers.data?.items || []).map((p) => toCardProduct(p, locale))}
            testId="best-sellers-grid"
          />
        )}
      </section>

      <EditorialSection stories={cmsBundle?.stories} />
    </div>
  );
}
