import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCmsNavigation } from "@/lib/api";
import { pickCmsLocalized } from "@/lib/localize";

const ITEMS = [
  { key: "nav.newArrivals", badge: "new" },
  { key: "nav.bestSellers", badge: "bestseller" },
  { key: "nav.sale", badge: "sale" },
];

export default function SecondaryNav() {
  const { locale, t } = useI18n();
  const [searchParams] = useSearchParams();
  const activeBadge = searchParams.get("badge");
  const query = useQuery({
    queryKey: ["cms", "navigation"],
    queryFn: getCmsNavigation,
    staleTime: 60_000,
  });
  if (query.isLoading) return null;
  const items = query.isError
    ? ITEMS.map((item) => ({
        slug: item.key,
        cta_url: `/shop?badge=${item.badge}`,
        translations: { [locale]: { title: t(item.key) } },
      }))
    : (query.data?.items || []).filter((item) => item.placement === "secondary");
  if (!items.length) return null;
  return (
    <nav data-testid="secondary-nav" className="border-b border-border">
      <div className="mx-auto flex w-full max-w-[1440px] items-center gap-6 overflow-x-auto px-4 sm:px-6 lg:justify-center lg:px-10">
        {items.map((item) => {
          const href = item.cta_url || "/shop";
          const title = pickCmsLocalized(item.translations, locale);
          const active = activeBadge && href.includes(`badge=${activeBadge}`);
          const className = `whitespace-nowrap border-b-2 py-2.5 text-[13px] transition-colors ${
            active
              ? "border-foreground font-semibold text-foreground"
              : "border-transparent text-muted-foreground hover:border-brand-gold hover:text-foreground"
          }`;
          const testId = `secondary-nav-${(item.slug || item.id || "item").replace(/[^a-z0-9-]/gi, "-")}`;
          return href.startsWith("/") ? (
          <Link
            key={item.id || item.slug}
            to={href}
            data-testid={testId}
            className={className}
          >
            {title}
          </Link>
          ) : (
            <a key={item.id || item.slug} href={href} data-testid={testId} className={className}>
              {title}
            </a>
          );
        })}
      </div>
    </nav>
  );
}
