import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCatalogTree, getCmsBundle, getProducts } from "@/lib/api";
import { mediaUrl, mediaVariantUrl, pickCmsLocalized, pickLocalized, toCardProduct } from "@/lib/localize";
import { DEPARTMENT_VISUALS } from "@/lib/catalogVisuals";
import CategoryStrip from "@/components/common/CategoryStrip";
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

const LEGACY_SECTION_ALIASES = {
  curated_primary: "new_arrivals",
  curated_secondary: "best_sellers",
};

const PRODUCT_SECTION_CONFIG = {
  best_sellers: { fallbackTitle: "Terlaris", testId: "home-best-sellers" },
  new_arrivals: { fallbackTitle: "Koleksi Terbaru", testId: "home-new-arrivals" },
  skincare: { fallbackTitle: "Rawat Kulitmu", testId: "home-skincare" },
  daily_style: { fallbackTitle: "Gaya Sehari-hari", testId: "home-daily-style" },
};

const HOMEPAGE_RENDER_ORDER = [
  "categories",
  "best_sellers",
  "new_arrivals",
  "skincare",
  "daily_style",
];

function canonicalSectionKey(key) {
  return LEGACY_SECTION_ALIASES[key] || key;
}

function sectionProducts(section, fallbackProducts, featuredProducts, curatedProducts) {
  const payload = section?.payload || {};
  const canonicalKey = canonicalSectionKey(section?.key);
  const selectedIds = Array.isArray(payload.product_ids) ? payload.product_ids : [];
  const byId = new Map([...fallbackProducts, ...featuredProducts, ...curatedProducts].map((product) => [product.id, product]));
  if (selectedIds.length) return selectedIds.map((id) => byId.get(id)).filter(Boolean).slice(0, 24);
  if (PRODUCT_SECTION_CONFIG[canonicalKey] && section?.sourceKey === canonicalKey) return [];
  const source = payload.sort || (canonicalKey === "best_sellers" ? "featured" : "newest");
  const sourceProducts = source === "featured" && featuredProducts.length ? featuredProducts : fallbackProducts;
  return sourceProducts.slice(0, Math.min(Number(payload.limit) || 8, 24));
}

export default function HomePage() {
  const { locale, t } = useI18n();
  const catalogQuery = useQuery({ queryKey: ["catalog-tree"], queryFn: getCatalogTree, staleTime: 5 * 60 * 1000 });
  const cmsBundleQuery = useQuery({ queryKey: ["cms", "bundle"], queryFn: getCmsBundle, staleTime: 60_000 });

  const cmsBundle = cmsBundleQuery.data;
  const cmsFailed = cmsBundleQuery.isError;
  const departments = (catalogQuery.data || []).filter((node) => node.kind === "department" && node.is_active !== false).sort((a, b) => a.sort_order - b.sort_order);
  const departmentVisuals = Object.fromEntries((cmsBundle?.department_visuals || []).map((visual) => [visual.slug, visual]));
  const hasProductsInNode = (node) => Number(node.product_count || 0) > 0 || (node.children || []).some((child) => hasProductsInNode(child));
  const catalogReady = catalogQuery.isSuccess;
  const comingSoonLabel = locale === "id" ? "Segera hadir" : locale === "uz" ? "Tez orada" : locale === "ru" ? "Скоро" : "Coming soon";
  const departmentCards = departments.map((department) => ({
    ...department,
    image: !catalogReady || hasProductsInNode(department)
      ? DEPARTMENT_VISUALS[department.slug] || mediaUrl(departmentVisuals[department.slug]?.image_url) || department.image_url || ""
      : "",
    comingSoon: catalogReady && !hasProductsInNode(department),
    comingSoonLabel,
    name: pickLocalized(department.translations, locale),
  }));
  const sections = useMemo(() => cmsBundle?.sections || [], [cmsBundle?.sections]);
  const hero = cmsBundle?.hero;
  const heroProductId = hero?.payload?.product_id;
  const selectedProductIds = [...new Set([...sections.flatMap((section) => (
    Array.isArray(section.payload?.product_ids) ? section.payload.product_ids : []
  )), ...(heroProductId ? [heroProductId] : [])])];
  const fallbackSorts = [...new Set(sections.flatMap((section) => {
    const canonicalKey = canonicalSectionKey(section.key);
    const isLegacySection = PRODUCT_SECTION_CONFIG[canonicalKey] && section.key !== canonicalKey;
    if (!isLegacySection || section.payload?.product_ids?.length) return [];
    return [section.payload?.sort === "featured" || (!section.payload?.sort && canonicalKey === "best_sellers") ? "featured" : "newest"];
  }))];
  if (hero && !hero.payload?.hero_asset_url) fallbackSorts.push(heroProductId ? "newest" : "featured");
  const productsByIdQuery = useQuery({
    queryKey: ["products", "home-selected", selectedProductIds.join(",")],
    queryFn: () => getProducts({ ids: selectedProductIds.join(","), limit: selectedProductIds.length }),
    enabled: selectedProductIds.length > 0,
    staleTime: 60_000,
  });
  const fallbackNewestQuery = useQuery({
    queryKey: ["products", "home-fallback-newest"],
    queryFn: () => getProducts({ sort: "newest", limit: 24 }),
    enabled: cmsBundleQuery.isSuccess && fallbackSorts.includes("newest"),
    staleTime: 60_000,
  });
  const fallbackFeaturedQuery = useQuery({
    queryKey: ["products", "home-fallback-featured"],
    queryFn: () => getProducts({ sort: "featured", limit: 24 }),
    enabled: cmsBundleQuery.isSuccess && fallbackSorts.includes("featured"),
    staleTime: 60_000,
  });
  const curatedProducts = productsByIdQuery.data?.items || [];
  const fallbackProducts = fallbackNewestQuery.data?.items || [];
  const featuredProducts = fallbackFeaturedQuery.data?.items || [];
  const sectionByKey = sections.reduce((result, section) => {
    const key = canonicalSectionKey(section.key);
    if (!result[key] || section.key === key) result[key] = { ...section, key, sourceKey: section.key };
    return result;
  }, {});
  const allLoadedProducts = new Map([...fallbackProducts, ...featuredProducts, ...curatedProducts].map((product) => [product.id, product]));
  const heroProduct = allLoadedProducts.get(heroProductId) || featuredProducts[0] || fallbackProducts[0];
  const heroMedia = heroProduct?.media?.[0];
  const catalogHeroImage = typeof heroMedia === "string" ? heroMedia : heroMedia?.url || "";
  const heroImage = hero?.payload?.hero_asset_url || catalogHeroImage;
  const heroMediaType = hero?.payload?.hero_media_type || (/\.(mp4|webm|mov)(\?|$)/i.test(heroImage) ? "video" : "image");
  const heroMobileImage = heroMediaType === "image" ? hero?.payload?.hero_mobile_asset_url || "" : "";
  const heroTitle = pickCmsLocalized(hero?.translations, locale) || (cmsFailed ? t("page.home.heroTitle") : "");
  const heroEyebrow = pickCmsLocalized(hero?.translations, locale, "eyebrow") || (cmsFailed ? t("brand.tagline") : "");
  const heroSubtitle = pickCmsLocalized(hero?.translations, locale, "subtitle") || (cmsFailed ? t("page.home.heroSubtitle") : "");
  const heroAlt = heroProduct ? `${heroProduct.brand || ""} ${pickLocalized(heroProduct.translations, locale)}`.trim() : heroTitle;
  const heroPrimary = { label: pickCmsLocalized(hero?.translations, locale, "cta_label") || (cmsFailed ? t("home.shopNow") : ""), to: hero?.cta_url || "/shop" };
  const heroSecondary = { label: pickCmsLocalized(hero?.translations, locale, "secondary_cta_label") || (cmsFailed ? t("home.allDepartments") : ""), to: hero?.secondary_cta_url || "/shop" };
  const sectionOrder = useMemo(() => {
    const available = new Set(sections.map((section) => canonicalSectionKey(section.key)));
    available.add("categories");
    return HOMEPAGE_RENDER_ORDER.filter((key) => available.has(key));
  }, [sections]);

  const renderProductSection = (section, fallbackTitle, testId) => {
    if (!section) return null;
    const products = sectionProducts(section, fallbackProducts, featuredProducts, curatedProducts);
    const hasProductError = productsByIdQuery.isError || fallbackNewestQuery.isError || fallbackFeaturedQuery.isError;
    const productsLoading = productsByIdQuery.isLoading || fallbackNewestQuery.isLoading || fallbackFeaturedQuery.isLoading;
    if (hasProductError) return <section key={testId} data-testid={testId} className="py-6"><ErrorState onRetry={() => { if (selectedProductIds.length) productsByIdQuery.refetch(); if (fallbackSorts.includes("newest")) fallbackNewestQuery.refetch(); if (fallbackSorts.includes("featured")) fallbackFeaturedQuery.refetch(); }} /></section>;
    if (productsLoading) return <section key={testId} data-testid={testId} className="py-6"><GridSkeleton testId={`${testId}-loading`} /></section>;
    if (!products.length) return null;
    const title = section.sourceKey !== section.key
      ? fallbackTitle
      : pickCmsLocalized(section.translations, locale) || fallbackTitle;
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
        <CategoryStrip categories={departmentCards} nameOf={(department) => department.name} linkFor={(department) => `/shop?department=${department.slug}`} testIdPrefix="department-card" fillDesktop />
      </section>
    ) : catalogQuery.isLoading ? (
      <section key="categories-loading" data-testid="home-departments-loading" aria-busy="true" className="py-10 lg:py-12">
        <Skeleton className="mb-5 h-6 w-40" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="aspect-[4/3] w-full" />)}
        </div>
      </section>
    ) : null,
  };
  Object.entries(PRODUCT_SECTION_CONFIG).forEach(([key, config]) => {
    content[key] = renderProductSection(sectionByKey[key], config.fallbackTitle, config.testId);
  });
  const renderedSections = [];
  for (const key of sectionOrder) {
    if (PRODUCT_SECTION_CONFIG[key]) renderedSections.push(content[key]);
    else if (key === "categories" || key === "departments") renderedSections.push(content.categories);
  }

  return (
    <div data-testid="home-page">
      {hero || cmsFailed ? (
        <section data-testid="home-hero" className="relative left-1/2 w-screen -translate-x-1/2 overflow-hidden bg-brand-ivory">
          <div className="relative">
            {heroImage ? heroMediaType === "video" ? (
              <video src={mediaUrl(heroImage)} poster={hero?.payload?.hero_poster_url ? mediaUrl(hero.payload.hero_poster_url) : undefined} autoPlay muted loop playsInline preload="metadata" aria-label={heroAlt} className="block h-auto w-full object-contain" />
            ) : (
              <picture className="block">
                {heroMobileImage ? <source media="(max-width: 1023px)" srcSet={mediaVariantUrl(heroMobileImage, 1280)} /> : null}
                <ImageWithFallback src={mediaVariantUrl(heroImage, 1920)} alt={heroAlt} className="block h-auto w-full object-contain" />
              </picture>
            ) : <div className="h-[45vh] min-h-[360px] bg-brand-ivory" />}
            <div className="bg-brand-ivory px-4 pb-8 pt-7 text-foreground sm:px-8 sm:pb-12 lg:absolute lg:inset-0 lg:flex lg:items-end lg:bg-transparent lg:bg-gradient-to-r lg:from-black/45 lg:via-black/10 lg:to-transparent lg:px-12 lg:pb-16 lg:pt-20 lg:text-white">
              <div className="w-full">
                {heroEyebrow ? <p className="text-[11px] font-medium uppercase tracking-[0.2em] sm:text-xs">{heroEyebrow}</p> : null}
                {heroTitle ? <h1 className="mt-2 max-w-xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">{heroTitle}</h1> : null}
                {heroSubtitle ? <p className="mt-2 max-w-xl text-sm text-foreground/70 lg:text-white/85">{heroSubtitle}</p> : null}
                <div className="mt-5 flex flex-wrap items-center gap-3">
                  {heroPrimary.label ? <Link to={heroPrimary.to} data-testid="hero-cta-shop" className="rounded-full bg-background px-6 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-secondary">{heroPrimary.label}</Link> : null}
                  {heroSecondary.label ? <Link to={heroSecondary.to} data-testid="hero-cta-departments" className="rounded-full border border-foreground/30 px-6 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-foreground/10 lg:border-white/70 lg:text-white lg:hover:bg-white/10">{heroSecondary.label}</Link> : null}
                </div>
              </div>
            </div>
          </div>
        </section>
      ) : cmsBundleQuery.isLoading ? (
        <section data-testid="home-hero-loading" aria-busy="true" className="relative left-1/2 w-screen -translate-x-1/2 overflow-hidden">
          <Skeleton className="h-[42vh] min-h-[280px] w-full rounded-none" />
        </section>
      ) : null}
      <CmsBannerStrip banners={cmsBundle?.banners || []} />
      {catalogQuery.isError ? <ErrorState onRetry={() => catalogQuery.refetch()} /> : renderedSections}
    </div>
  );
}
