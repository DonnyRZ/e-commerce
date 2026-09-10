import { Link } from "react-router-dom";
import { Facebook, Instagram, Youtube } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCmsFooter } from "@/lib/api";
import { pickLocalized } from "@/lib/localize";
import LanguageSelector from "./LanguageSelector";
import BrandLogo from "@/components/brand/BrandLogo";

const FALLBACK_GROUPS = [
  {
    heading: "footer.shop",
    links: [
      ["footer.link.newArrivals", "/shop?badge=new"],
      ["footer.link.bestSellers", "/shop?badge=bestseller"],
      ["nav.womenMuslimah", "/shop?department=women-muslimah"],
      ["nav.uniqloProducts", "/shop?department=uniqlo-products"],
      ["nav.skincare", "/shop?department=tropical-halal-skincare"],
    ],
  },
  {
    heading: "footer.help",
    links: [
      ["footer.link.contact", "mailto:hello@muslimahcantik.id"],
      ["footer.link.shipping", "/page/shipping"],
      ["footer.link.returns", "/page/returns"],
      ["footer.link.faq", "/faq"],
    ],
  },
  {
    heading: "footer.account",
    links: [
      ["footer.link.myAccount", "/account"],
      ["header.wishlist", "/wishlist"],
      ["footer.link.orders", "/orders"],
    ],
  },
  {
    heading: "footer.about",
    links: [
      ["footer.link.aboutUs", "/page/about"],
      ["footer.link.privacy", "/page/privacy"],
      ["footer.link.terms", "/page/terms"],
    ],
  },
];

const SOCIALS = [
  { icon: Facebook, label: "Facebook", url: process.env.REACT_APP_FACEBOOK_URL },
  { icon: Instagram, label: "Instagram", url: process.env.REACT_APP_INSTAGRAM_URL },
  { icon: Youtube, label: "YouTube", url: process.env.REACT_APP_YOUTUBE_URL },
];

const linkClass =
  "cursor-pointer text-sm font-medium text-foreground transition-colors hover:text-primary hover:underline";

export default function Footer() {
  const { locale, t } = useI18n();
  const { data: cmsFooter } = useQuery({
    queryKey: ["cms", "footer"],
    queryFn: getCmsFooter,
    staleTime: 60_000,
  });

  const cmsGroups = (cmsFooter?.groups || [])
    .map((g) => ({
      key: g.slug,
      heading: pickLocalized(g.translations, locale),
      items: (g.items || []).map((i) => ({
        key: i.slug || i.id,
        label: pickLocalized(i.translations, locale),
        to: i.cta_url,
      })),
    }))
    .filter((g) => g.items.length);

  const promo =
    pickLocalized(cmsFooter?.promo?.translations, locale) ||
    pickLocalized(cmsFooter?.promo?.translations, locale, "description") ||
    t("footer.promo");

  return (
    <footer data-testid="site-footer" className="border-t border-brand-gold/30 bg-brand-ivory/60">
      <div className="mx-auto w-full max-w-[1440px] px-4 py-10 sm:px-6 lg:px-10 lg:py-12">
        <div className="mb-10 flex items-center justify-between gap-6 border-b border-brand-gold/30 pb-8">
          <BrandLogo size="lg" to="/" testId="footer-brand-logo" />
        </div>
        {cmsGroups.length
          ? cmsGroups.map((group) => (
              <div key={group.key} className="mb-6">
                <h3 className="mb-2 text-sm text-muted-foreground">{group.heading}</h3>
                <ul
                  className="flex flex-wrap items-center gap-x-3 gap-y-1.5"
                  data-testid={`footer-group-${group.key}`}
                >
                  {group.items.map((item, i) => (
                    <li key={item.key} className="flex items-center gap-3">
                      {item.to?.startsWith("/") ? (
                        <Link to={item.to} data-testid={`footer-link-${item.key}`} className={linkClass}>
                          {item.label}
                        </Link>
                      ) : item.to?.startsWith("http") || item.to?.startsWith("mailto:") ? (
                        <a
                          href={item.to}
                          target={item.to.startsWith("http") ? "_blank" : undefined}
                          rel={item.to.startsWith("http") ? "noreferrer" : undefined}
                          data-testid={`footer-link-${item.key}`}
                          className={linkClass}
                        >
                          {item.label}
                        </a>
                      ) : (
                        <span data-testid={`footer-link-${item.key}`} className="text-sm font-medium text-muted-foreground">
                          {item.label}
                        </span>
                      )}
                      {i < group.items.length - 1 ? (
                        <span className="text-muted-foreground" aria-hidden="true">
                          |
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          : FALLBACK_GROUPS.map((group) => (
              <div key={group.heading} className="mb-6">
                <h3 className="mb-2 text-sm text-muted-foreground">{t(group.heading)}</h3>
                <ul
                  className="flex flex-wrap items-center gap-x-3 gap-y-1.5"
                  data-testid={`footer-group-${group.heading.split(".")[1]}`}
                >
                  {group.links.map(([key, to], i) => (
                    <li key={key} className="flex items-center gap-3">
                      {to.startsWith("/") ? (
                        <Link
                          to={to}
                          data-testid={`footer-link-${key.split(".").pop()}`}
                          className={linkClass}
                        >
                          {t(key)}
                        </Link>
                      ) : (
                        <a
                          href={to}
                          data-testid={`footer-link-${key.split(".").pop()}`}
                          className={linkClass}
                        >
                          {t(key)}
                        </a>
                      )}
                      {i < group.links.length - 1 ? (
                        <span className="text-muted-foreground" aria-hidden="true">
                          |
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
        <p data-testid="footer-promo" className="mt-8 text-sm font-semibold">
          {promo}
        </p>
        <div className="mt-8 flex flex-col gap-4 border-t border-border pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p data-testid="footer-rights" className="text-xs text-muted-foreground">
            {t("footer.rights")}
          </p>
          <div className="flex items-center gap-2">
            <LanguageSelector />
            {SOCIALS.filter((social) => social.url).map(({ icon: Icon, label, url }) => (
              <a
                key={label}
                href={url}
                target="_blank"
                rel="noreferrer"
                data-testid={`footer-social-${label.toLowerCase()}`}
                aria-label={label}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-80"
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
              </a>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}
