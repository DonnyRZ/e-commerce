import { useI18n } from "@/i18n";

export default function HomePage() {
  const { t } = useI18n();
  return (
    <section data-testid="home-page" className="py-16 sm:py-24 lg:py-32">
      <div className="max-w-2xl">
        <p className="text-sm font-medium uppercase tracking-widest text-primary">
          {t("brand.tagline")}
        </p>
        <h1 className="mt-4 text-4xl font-bold leading-tight tracking-tight sm:text-5xl lg:text-6xl">
          {t("page.home.heroTitle")}
        </h1>
        <p className="mt-6 text-base text-muted-foreground md:text-lg">
          {t("page.home.heroSubtitle")}
        </p>
        <p
          data-testid="home-placeholder-note"
          className="mt-10 text-sm text-muted-foreground"
        >
          {t("page.home.placeholderNote")}
        </p>
      </div>
    </section>
  );
}
