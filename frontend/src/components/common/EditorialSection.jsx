import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useI18n } from "@/i18n";
import { EDITORIALS, localizedField } from "@/data/demo";
import { mediaUrl, pickCmsLocalized } from "@/lib/localize";
import ImageWithFallback from "./ImageWithFallback";

export default function EditorialSection({ stories, title, cmsFailed = false }) {
  const { locale, t } = useI18n();
  const items = stories?.length
    ? stories.map((s) => ({
        id: s.id,
        slug: s.slug,
        image: mediaUrl(s.image_url),
        label: pickCmsLocalized(s.translations, locale, "eyebrow"),
        title: pickCmsLocalized(s.translations, locale),
        alt: pickCmsLocalized(s.translations, locale, "alt_text"),
        description: pickCmsLocalized(s.translations, locale, "description"),
        ctaLabel: pickCmsLocalized(s.translations, locale, "cta_label") || (cmsFailed ? t("editorial.cta") : ""),
        href: s.cta_url || (cmsFailed ? "/shop" : ""),
      }))
    : cmsFailed ? EDITORIALS.map((item) => ({
        id: item.id,
        slug: item.slug,
        image: item.image,
        label: localizedField(item, "labels", locale),
        title: localizedField(item, "titles", locale),
        alt: localizedField(item, "titles", locale),
        description: localizedField(item, "descriptions", locale),
        ctaLabel: t("editorial.cta"),
        href: "/shop",
      })) : [];

  if (!items.length) return null;
  const sectionTitle = title || (cmsFailed ? t("editorial.title") : "");

  return (
    <section data-testid="home-editorial" className="py-10 lg:py-14">
      {sectionTitle ? <h2 className="mb-5 text-lg font-semibold lg:text-xl">{sectionTitle}</h2> : null}
      <div className="grid gap-x-4 gap-y-8 sm:grid-cols-2 lg:grid-cols-4 lg:gap-x-5">
        {items.map((item) => (
          <article key={item.id} data-testid={`editorial-card-${item.slug}`} className="group">
            {item.href ? <Link to={item.href} className="block overflow-hidden bg-secondary">
              <ImageWithFallback
                src={item.image}
                alt={item.alt || item.title}
                loading="lazy"
                className="aspect-[4/3] w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
            </Link> : <div className="overflow-hidden bg-secondary"><ImageWithFallback src={item.image} alt={item.alt || item.title} loading="lazy" className="aspect-[4/3] w-full object-cover" /></div>}
            <p className="mt-3 text-[11px] font-medium uppercase tracking-widest text-primary">
              {item.label}
            </p>
            <h3 className="mt-1 text-sm font-semibold leading-snug lg:text-base">
              {item.href ? <Link to={item.href} className="hover:underline">
                {item.title}
              </Link> : item.title}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {item.description}
            </p>
            {item.href && item.ctaLabel ? <Link
              to={item.href}
              data-testid={`editorial-cta-${item.slug}`}
              className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-foreground underline-offset-4 hover:underline"
            >
              {item.ctaLabel}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
