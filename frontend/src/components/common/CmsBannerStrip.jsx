import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { useI18n } from "@/i18n";
import { mediaVariantUrl, pickCmsLocalized } from "@/lib/localize";
import ImageWithFallback from "./ImageWithFallback";

function BannerCard({ banner, locale }) {
  const title = pickCmsLocalized(banner.translations, locale);
  const eyebrow = pickCmsLocalized(banner.translations, locale, "eyebrow");
  const description = pickCmsLocalized(banner.translations, locale, "description");
  const ctaLabel = pickCmsLocalized(banner.translations, locale, "cta_label");
  const image = mediaVariantUrl(banner.image_url, 1280);
  const href = banner.cta_url;
  const content = (
    <>
      {image ? (
        <ImageWithFallback
          src={image}
          alt={pickCmsLocalized(banner.translations, locale, "alt_text") || title}
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.03]"
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-r from-brand-forest/90 via-brand-forest/55 to-transparent" />
      <div className="relative z-10 flex min-h-52 max-w-xl flex-col items-start justify-center p-6 text-white sm:min-h-64 sm:p-9">
        {eyebrow ? <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-brand-gold">{eyebrow}</p> : null}
        <h2 className="mt-2 font-serif text-2xl font-semibold leading-tight sm:text-3xl">{title}</h2>
        {description ? <p className="mt-2 max-w-md text-sm leading-6 text-white/85">{description}</p> : null}
        {ctaLabel ? (
          <span className="mt-4 inline-flex items-center gap-2 border-b border-brand-gold pb-1 text-xs font-semibold uppercase tracking-[0.12em]">
            {ctaLabel}<ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
        ) : null}
      </div>
    </>
  );

  if (!href) return <article className="group relative isolate overflow-hidden rounded-sm bg-brand-forest">{content}</article>;
  if (href.startsWith("/")) return <Link to={href} className="group relative isolate block overflow-hidden rounded-sm bg-brand-forest">{content}</Link>;
  return <a href={href} target="_blank" rel="noreferrer" className="group relative isolate block overflow-hidden rounded-sm bg-brand-forest">{content}</a>;
}

export default function CmsBannerStrip({ banners = [] }) {
  const { locale } = useI18n();
  const visible = banners.filter((banner) => pickCmsLocalized(banner.translations, locale));
  if (!visible.length) return null;
  return (
    <section data-testid="home-cms-banners" className="py-8 lg:py-10">
      <div className={`grid gap-4 ${visible.length > 1 ? "md:grid-cols-2" : "grid-cols-1"}`}>
        {visible.map((banner) => <BannerCard key={banner.id} banner={banner} locale={locale} />)}
      </div>
    </section>
  );
}
