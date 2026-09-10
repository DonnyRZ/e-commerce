import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useI18n } from "@/i18n";
import { EDITORIALS, localizedField } from "@/data/demo";
import { mediaUrl, pickLocalized } from "@/lib/localize";

export default function EditorialSection({ stories }) {
  const { locale, t } = useI18n();
  const items = stories?.length
    ? stories.map((s) => ({
        id: s.id,
        slug: s.slug,
        image: mediaUrl(s.image_url),
        label: pickLocalized(s.translations, locale, "eyebrow"),
        title: pickLocalized(s.translations, locale),
        description: pickLocalized(s.translations, locale, "description"),
        ctaLabel: pickLocalized(s.translations, locale, "cta_label") || t("editorial.cta"),
        href: s.cta_url || "/shop",
      }))
    : EDITORIALS.map((item) => ({
        id: item.id,
        slug: item.slug,
        image: item.image,
        label: localizedField(item, "labels", locale),
        title: localizedField(item, "titles", locale),
        description: localizedField(item, "descriptions", locale),
        ctaLabel: t("editorial.cta"),
        href: "/shop",
      }));

  return (
    <section data-testid="home-editorial" className="py-10 lg:py-14">
      <h2 className="mb-5 text-lg font-semibold lg:text-xl">
        {t("editorial.title")}
      </h2>
      <div className="grid gap-x-4 gap-y-8 sm:grid-cols-2 lg:grid-cols-4 lg:gap-x-5">
        {items.map((item) => (
          <article key={item.id} data-testid={`editorial-card-${item.slug}`} className="group">
            <Link to={item.href} className="block overflow-hidden bg-secondary">
              <img
                src={item.image}
                alt={item.title}
                loading="lazy"
                className="aspect-[4/3] w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
            </Link>
            <p className="mt-3 text-[11px] font-medium uppercase tracking-widest text-primary">
              {item.label}
            </p>
            <h3 className="mt-1 text-sm font-semibold leading-snug lg:text-base">
              <Link to={item.href} className="hover:underline">
                {item.title}
              </Link>
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {item.description}
            </p>
            <Link
              to={item.href}
              data-testid={`editorial-cta-${item.slug}`}
              className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-foreground underline-offset-4 hover:underline"
            >
              {item.ctaLabel}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
