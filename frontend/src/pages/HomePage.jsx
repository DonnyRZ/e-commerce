import { Link } from "react-router-dom";
import { useI18n } from "@/i18n";
import {
  CATEGORIES,
  DEMO_PRODUCTS,
  DEPARTMENTS,
  HERO_IMAGE,
  localizedName,
} from "@/data/demo";
import CategoryStrip from "@/components/common/CategoryStrip";
import EditorialSection from "@/components/common/EditorialSection";
import ProductGrid from "@/components/common/ProductGrid";

export default function HomePage() {
  const { locale, t } = useI18n();
  const nameOf = (obj) => localizedName(obj, locale);

  return (
    <div data-testid="home-page">
      <section
        data-testid="home-hero"
        className="relative -mx-4 sm:-mx-6 lg:-mx-10"
      >
        <img
          src={HERO_IMAGE}
          alt={t("page.home.heroTitle")}
          className="h-[60vh] w-full object-cover lg:h-[72vh]"
        />
        <div className="absolute inset-x-0 bottom-0 pb-8 pt-24 text-center text-white [background:linear-gradient(to_top,rgba(0,0,0,0.55),transparent)] lg:pb-12">
          <p className="text-[11px] font-medium uppercase tracking-[0.2em] sm:text-xs">
            {t("brand.tagline")}
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">
            {t("page.home.heroTitle")}
          </h1>
          <p className="mx-auto mt-2 max-w-xl px-4 text-sm text-white/85">
            {t("page.home.heroSubtitle")}
          </p>
          <div className="mt-5 flex items-center justify-center gap-3">
            <Link
              to="/shop"
              data-testid="hero-cta-shop"
              className="rounded-full bg-background px-6 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
            >
              {t("home.shopNow")}
            </Link>
            <Link
              to="/shop"
              data-testid="hero-cta-departments"
              className="rounded-full border border-white/70 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/10"
            >
              {t("home.allDepartments")}
            </Link>
          </div>
        </div>
      </section>

      <section data-testid="home-categories" className="py-10 lg:py-14">
        <h2 className="mb-5 text-lg font-semibold lg:text-xl">
          {t("home.shopByCategory")}
        </h2>
        <CategoryStrip categories={CATEGORIES.slice(0, 8)} nameOf={nameOf} />
      </section>

      <section data-testid="home-new-arrivals" className="py-4 lg:py-6">
        <div className="mb-5 flex items-end justify-between">
          <h2 className="text-lg font-semibold lg:text-xl">
            {t("home.newArrivals")}
          </h2>
          <Link
            to="/shop"
            data-testid="new-arrivals-view-all"
            className="text-sm font-medium text-foreground underline-offset-4 hover:underline"
          >
            {t("home.viewAll")}
          </Link>
        </div>
        <ProductGrid products={DEMO_PRODUCTS.slice(0, 8)} testId="new-arrivals-grid" />
      </section>

      <section data-testid="home-departments" className="py-10 lg:py-14">
        <div className="grid gap-4 sm:grid-cols-3 lg:gap-5">
          {DEPARTMENTS.map((dept) => (
            <Link
              key={dept.id}
              to="/shop"
              data-testid={`department-tile-${dept.slug}`}
              className="group relative block overflow-hidden bg-secondary"
            >
              <img
                src={dept.image}
                alt={nameOf(dept)}
                loading="lazy"
                className="aspect-[4/5] w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
              <div className="absolute inset-x-0 bottom-0 flex items-center justify-between p-4 text-white [background:linear-gradient(to_top,rgba(0,0,0,0.55),transparent)]">
                <span className="text-sm font-semibold">{nameOf(dept)}</span>
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
          <h2 className="text-lg font-semibold lg:text-xl">
            {t("home.bestSellers")}
          </h2>
          <Link
            to="/shop"
            data-testid="best-sellers-view-all"
            className="text-sm font-medium text-foreground underline-offset-4 hover:underline"
          >
            {t("home.viewAll")}
          </Link>
        </div>
        <ProductGrid
          products={[...DEMO_PRODUCTS.slice(2), ...DEMO_PRODUCTS.slice(0, 2)]}
          testId="best-sellers-grid"
        />
      </section>

      <EditorialSection />
    </div>
  );
}
