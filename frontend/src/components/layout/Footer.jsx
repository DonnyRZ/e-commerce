import { Link } from "react-router-dom";
import { useI18n } from "@/i18n";

const COLUMNS = [
  {
    heading: "footer.shop",
    links: ["footer.link.newArrivals", "footer.link.bestSellers", "nav.womenMuslimah", "nav.apparel", "nav.skincare"],
  },
  {
    heading: "footer.help",
    links: ["footer.link.contact", "footer.link.shipping", "footer.link.returns", "footer.link.faq"],
  },
  {
    heading: "footer.about",
    links: ["footer.link.aboutUs", "footer.link.stores", "footer.link.privacy", "footer.link.terms"],
  },
];

export default function Footer() {
  const { t } = useI18n();
  return (
    <footer data-testid="site-footer" className="border-t border-border bg-secondary/40">
      <div className="mx-auto w-full max-w-[1440px] px-4 py-10 sm:px-6 lg:px-10 lg:py-14">
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Link
              to="/"
              data-testid="footer-brand"
              className="text-sm font-bold tracking-widest"
            >
              {t("brand.name")}
            </Link>
            <p className="mt-3 max-w-xs text-sm text-muted-foreground">
              {t("footer.description")}
            </p>
          </div>
          {COLUMNS.map((col) => (
            <div key={col.heading}>
              <h3 className="text-sm font-semibold">{t(col.heading)}</h3>
              <ul className="mt-3 space-y-2">
                {col.links.map((key) => (
                  <li
                    key={key}
                    data-testid={`footer-link-${key.split(".").pop()}`}
                    className="cursor-pointer text-sm text-muted-foreground transition-colors hover:text-primary hover:underline"
                  >
                    {t(key)}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div
          data-testid="footer-rights"
          className="mt-10 border-t border-border pt-6 text-xs text-muted-foreground"
        >
          {t("footer.rights")}
        </div>
      </div>
    </footer>
  );
}
