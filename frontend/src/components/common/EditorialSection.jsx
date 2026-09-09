import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useI18n } from "@/i18n";
import { EDITORIALS, localizedField } from "@/data/demo";

export default function EditorialSection() {
  const { locale, t } = useI18n();
  return (
    <section data-testid="home-editorial" className="py-10 lg:py-14">
      <h2 className="mb-5 text-lg font-semibold lg:text-xl">
        {t("editorial.title")}
      </h2>
      <div className="grid gap-x-4 gap-y-8 sm:grid-cols-2 lg:grid-cols-4 lg:gap-x-5">
        {EDITORIALS.map((item) => (
          <article key={item.id} data-testid={`editorial-card-${item.slug}`} className="group">
            <Link to="/shop" className="block overflow-hidden bg-secondary">
              <img
                src={item.image}
                alt={localizedField(item, "titles", locale)}
                loading="lazy"
                className="aspect-[4/3] w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
            </Link>
            <p className="mt-3 text-[11px] font-medium uppercase tracking-widest text-primary">
              {localizedField(item, "labels", locale)}
            </p>
            <h3 className="mt-1 text-sm font-semibold leading-snug lg:text-base">
              <Link to="/shop" className="hover:underline">
                {localizedField(item, "titles", locale)}
              </Link>
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {localizedField(item, "descriptions", locale)}
            </p>
            <Link
              to="/shop"
              data-testid={`editorial-cta-${item.slug}`}
              className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-foreground underline-offset-4 hover:underline"
            >
              {t("editorial.cta")}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
