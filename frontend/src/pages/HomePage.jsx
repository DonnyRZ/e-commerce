import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCatalogTree, getCmsBundle, getProducts } from "@/lib/api";
import { mediaUrl, pickCmsLocalized, pickLocalized, toCardProduct } from "@/lib/localize";
import CategoryStrip from "@/components/common/CategoryStrip";
import EditorialSection from "@/components/common/EditorialSection";
import CmsBannerStrip from "@/components/common/CmsBannerStrip";
import ProductRail from "@/components/common/ProductRail";
import ErrorState from "@/components/common/ErrorState";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";

function GridSkeleton({ testId }) {
  return (
    <div data-testid={testId} className="grid grid-cols-2 gap-x-3 gap-y-8 md:grid-cols-3 lg:grid-cols-4 lg:gap-x-5">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i}><Skeleton className="aspect-[3/4] w-full" /><Skeleton className="mt-3 h-4 w-3/4" /></div>
      ))}
    </div>
  );
}

const SECTION_ALIASES = {
  curated_primary: "curated_primary",
  new_arrivals: "curated_primary",
  curated_secondary: "curated_secondary",
  best_sellers: "curated_secondary",
};

function sectionProducts(section, fallbackProducts, featuredProducts, curatedProducts) {
  const payload = section?.payload || {};
  const selectedIds = Array.isArray(payload.product_ids) ? payload.product_ids : [];
  const byId = new Map([...fallbackProducts, ...featuredProducts, ...curatedProducts].map((product) => [product.id, product]));
  if (selectedIds.length) return selectedIds.map((id) => byId.get(id)).filter(Boolean).slice(0, 24);
  const source = payload.sort || (SECTION_ALIASES[section?.key] === "curated_secondary" ? "featured" : "newest");
  const sourceProducts = source === "featured" && featuredProducts.length ? featuredProducts : fallbackProducts;
  return sourceProducts.slice(0, Math.min(Number(payload.limit) || 8, 24));
}

export default function HomePage() {
  const { locale, t } = useI18n();
  const catalogQuery = useQuery({ queryKey: ["catalog-tree"], queryFn: getCatalogTree, staleTime: 5 * 60 * 1000 });
  const cmsBundleQuery = useQuery({ queryKey: ["cms", "bundle"], queryFn: getCmsBundle, staleTime: 60_000 });
  const catalogProductsQuery = useQuery({ queryKey: ["products", "home-catalog"], queryFn: () => getProducts({ sort: "newest", limit: 60 }), staleTime: 60_000 });
  const featuredProductsQuery = useQuery({ queryKey: ["products", "home-featured"], queryFn: () => getProducts({ sort: "featured", limit: 60 }), staleTime: 60_000 });

  const cmsBundle = cmsBundleQuery.data;
  const cmsFailed = cmsBundleQuery.isError;
  const departments = (catalogQuery.data || []).filter((node) => node.kind === "department" && node.is_active !== false).sort((a, b) => a.sort_order - b.sort_order);
  const departmentVisuals = Object.fromEntries((cmsBundle?.department_visuals || []).map((visual) => [visual.slug, visual]));
  const departmentCards = departments.map((department) => ({
    ...department,
    image: mediaUrl(departmentVisuals[department.slug]?.image_url) || department.image_url || "",
    name: pickLocalized(department.translations, locale),
  }));
  const fallbackProducts = catalogProductsQuery.data?.items || [];
  const featuredProducts = featuredProductsQuery.data?.items || [];
  const sections = useMemo(() => cmsBundle?.sections || [], [cmsBundle?.sections]);
  const selectedProductIds = [...new Set(sections.flatMap((section) => (
    Array.isArray(section.payload?.product_ids) ? section.payload.product_ids : []
  )))];
  const curatedProductsQuery = useQuery({
    queryKey: ["products", "home-curated", selectedProductIds.join(",")],
    queryFn: () => getProducts({ ids: selectedProductIds.join(","), limit: selectedProductIds.length }),
    enabled: selectedProductIds.length > 0,
    staleTime: 60_000,
  });
  const curatedProducts = curatedProductsQuery.data?.items || [];
  const sectionByKey = Object.fromEntries(sections.map((section) => [section.key, section]));
  const primarySection = sectionByKey.curated_primary || sectionByKey.new_arrivals;
  const secondarySection = sectionByKey.curated_secondary || sectionByKey.best_sellers;
  const hero = cmsBundle?.hero;
  const heroProductId = hero?.payload?.product_id;
  const heroProductQuery = useQuery({
    queryKey: ["products", "home-hero", heroProductId || "fallback"],
    queryFn: () => heroProductId ? getProducts({ ids: heroProductId, limit: 1 }) : getProducts({ sort: "featured", limit: 1 }),
    enabled: Boolean(cmsBundleQuery.isSuccess),
    staleTime: 60_000,
  });
  const heroProduct = heroProductQuery.data?.items?.[0] || fallbackProducts[0];
  const heroMedia = heroProduct?.media?.[0];
  const catalogHeroImage = typeof heroMedia === "string" ? heroMedia : heroMedia?.url || "";
  const heroImage = hero?.payload?.hero_asset_url || catalogHeroImage;
  const heroMediaType = hero?.payload?.hero_media_type || (/\.(mp4|webm|mov)(\?|$)/i.test(heroImage) ? "video" : "image");
  const heroTitle = pickCmsLocalized(hero?.translations, locale) || (cmsFailed ? t("page.home.heroTitle") : "");
  const heroEyebrow = pickCmsLocalized(hero?.translations, locale, "eyebrow") || (cmsFailed ? t("brand.tagline") : "");
  const heroSubtitle = pickCmsLocalized(hero?.translations, locale, "subtitle") || (cmsFailed ? t("page.home.heroSubtitle") : "");
  const heroAlt = heroProduct ? `${heroProduct.brand || ""} ${pickLocalized(heroProduct.translations, locale)}`.trim() : heroTitle;
  const heroPrimary = { label: pickCmsLocalized(hero?.translations, locale, "cta_label") || (cmsFailed ? t("home.shopNow") : ""), to: hero?.cta_url || "/shop" };
  const heroSecondary = { label: pickCmsLocalized(hero?.translations, locale, "secondary_cta_label") || (cmsFailed ? t("home.allDepartments") : ""), to: hero?.secondary_cta_url || "/shop" };
  const sectionOrder = useMemo(() => sections.filter((section) => section.key !== "hero" && section.key !== "footer" && section.key !== "promo_bar").sort((a, b) => a.sort_order - b.sort_order).map((section) => section.key), [sections]);

  const renderProductSection = (section, fallbackTitle, testId) => {
    if (!section || section.key === "stories") return null;
    const products = sectionProducts(section, fallbackProducts, featuredProducts, curatedProducts);
    if (catalogProductsQuery.isError || featuredProductsQuery.isError || curatedProductsQuery.isError) return <section key={testId} data-testid={testId} className="py-6"><ErrorState onRetry={() => { catalogProductsQuery.refetch(); featuredProductsQuery.refetch(); curatedProductsQuery.refetch(); }} /></section>;
    if (catalogProductsQuery.isLoading || featuredProductsQuery.isLoading || curatedProductsQuery.isLoading) return <section key={testId} data-testid={testId} className="py-6"><GridSkeleton testId={`${testId}-loading`} /></section>;
    if (!products.length) return null;
    const title = pickCmsLocalized(section.translations, locale) || fallbackTitle;
    return (
      <section key={testId} data-testid={testId} className="py-6 lg:py-8">
        <div className="mb-2 flex items-end justify-between gap-4"><h2 className="text-lg font-semibold lg:text-xl">{title}</h2><Link to="/shop" className="shrink-0 text-sm font-medium text-foreground underline-offset-4 hover:underline">{t("home.viewAll")}</Link></div>
        <ProductRail products={products.map((product) => toCardProduct(product, locale))} testId={`${testId}-rail`} />
      </section>
    );
  };

  const content = {
    categories: departmentCards.length ? (
      <section key="categories" data-testid="home-departments" className="py-10 lg:py-12">
        <h2 className="mb-5 text-lg font-semibold lg:text-xl">{pickCmsLocalized(sectionByKey.categories?.translations, locale) || t("home.shopByDepartment")}</h2>
        <CategoryStrip categories={departmentCards} nameOf={(department) => department.name} linkFor={(department) => `/shop?department=${department.slug}`} testIdPrefix="department-card" />
      </section>
    ) : null,
    primary: renderProductSection(primarySection, "Pilihan untukmu", "home-curated-primary"),
    secondary: renderProductSection(secondarySection, "Koleksi pilihan", "home-curated-secondary"),
    stories: <EditorialSection key="stories" stories={cmsBundle?.stories} title={pickCmsLocalized(cmsBundle?.story_title?.translations, locale)} cmsFailed={cmsFailed} />,
  };
  const renderedSections = [];
  for (const key of sectionOrder) {
    const alias = SECTION_ALIASES[key];
    if (alias === "curated_primary" && !renderedSections.some((item) => item?.key === "home-curated-primary")) renderedSections.push(content.primary);
    else if (alias === "curated_secondary" && !renderedSections.some((item) => item?.key === "home-curated-secondary")) renderedSections.push(content.secondary);
    else if (key === "categories") renderedSections.push(content.categories);
    else if (key === "stories") renderedSections.push(content.stories);
  }

  return (
    <div data-testid="home-page">
      {hero || cmsFailed ? (
        <section data-testid="home-hero" className="relative -mx-4 overflow-hidden bg-brand-ivory sm:-mx-6 lg:-mx-10 lg:h-[calc(100svh-8.25rem)] lg:min-h-[560px] lg:max-h-[820px]">
          <div className="relative lg:flex lg:h-full lg:w-full lg:items-center lg:justify-center">
            {heroImage ? heroMediaType === "video" ? (
              <video src={mediaUrl(heroImage)} poster={hero?.payload?.hero_poster_url ? mediaUrl(hero.payload.hero_poster_url) : undefined} autoPlay muted loop playsInline preload="metadata" aria-label={heroAlt} className="block h-auto w-full object-contain lg:h-full lg:w-full" />
            ) : (
              <ImageWithFallback src={mediaUrl(heroImage)} alt={heroAlt} className="block h-auto w-full object-contain lg:h-full lg:w-full" />
            ) : <div className="h-[45vh] min-h-[360px] bg-brand-ivory" />}
            <div className="bg-gradient-to-r from-black/45 via-black/10 to-transparent px-4 pb-8 pt-7 text-white sm:px-8 sm:pb-12 lg:absolute lg:inset-0 lg:flex lg:items-end lg:px-12 lg:pb-16 lg:pt-20">
              <div className="w-full">
                {heroEyebrow ? <p className="text-[11px] font-medium uppercase tracking-[0.2em] sm:text-xs">{heroEyebrow}</p> : null}
                {heroTitle ? <h1 className="mt-2 max-w-xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">{heroTitle}</h1> : null}
                {heroSubtitle ? <p className="mt-2 max-w-xl text-sm text-white/85">{heroSubtitle}</p> : null}
                <div className="mt-5 flex flex-wrap items-center gap-3">
                  {heroPrimary.label ? <Link to={heroPrimary.to} data-testid="hero-cta-shop" className="rounded-full bg-background px-6 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-secondary">{heroPrimary.label}</Link> : null}
                  {heroSecondary.label ? <Link to={heroSecondary.to} data-testid="hero-cta-departments" className="rounded-full border border-white/70 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/10">{heroSecondary.label}</Link> : null}
                </div>
              </div>
            </div>
          </div>
        </section>
      ) : null}
      <CmsBannerStrip banners={cmsBundle?.banners || []} />
      {catalogQuery.isError ? <ErrorState onRetry={() => catalogQuery.refetch()} /> : renderedSections}
    </div>
  );
}
