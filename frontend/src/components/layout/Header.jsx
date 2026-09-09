import { useState } from "react";
import { Link } from "react-router-dom";
import { Heart, Search, ShoppingBag, User } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getDepartments } from "@/lib/api";
import { pickLocalized } from "@/lib/localize";
import LanguageSelector from "./LanguageSelector";
import MobileNavigation from "./MobileNavigation";
import SecondaryNav from "./SecondaryNav";
import SearchOverlay from "./SearchOverlay";

const UTILITY_LINKS = [
  { key: "header.wishlist", to: "/wishlist", icon: Heart, testId: "wishlist-entry" },
  { key: "header.account", to: "/account", icon: User, testId: "account-entry" },
  { key: "header.cart", to: "/cart", icon: ShoppingBag, testId: "cart-entry" },
];

export default function Header() {
  const { locale, t } = useI18n();
  const [overlay, setOverlay] = useState({ open: false, dept: null });
  const { data: departments = [] } = useQuery({
    queryKey: ["departments"],
    queryFn: getDepartments,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <>
      <header data-testid="site-header" className="sticky top-0 z-40 bg-background">
        <div className="border-b border-border">
          <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center gap-2 px-4 sm:px-6 lg:h-16 lg:gap-4 lg:px-10">
            <MobileNavigation />
            <Link
              to="/"
              data-testid="brand-logo"
              className="text-sm font-extrabold tracking-widest sm:text-base"
            >
              {t("brand.name")}
            </Link>
            <nav
              className="ml-6 hidden items-center gap-7 lg:flex"
              aria-label="Primary"
              data-testid="desktop-nav"
            >
              {departments.map((dept) => (
                <Link
                  key={dept.id}
                  to={`/shop?department=${dept.slug}`}
                  data-testid={`nav-${dept.slug}`}
                  className="text-sm font-semibold tracking-wide text-foreground transition-colors hover:text-primary"
                >
                  {pickLocalized(dept.translations, locale)}
                </Link>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-0.5">
              <button
                type="button"
                data-testid="search-entry"
                aria-label={t("header.searchPlaceholder")}
                onClick={() => setOverlay({ open: true, dept: null })}
                className="inline-flex h-9 w-9 items-center justify-center text-foreground transition-colors hover:text-primary"
              >
                <Search className="h-5 w-5" aria-hidden="true" />
              </button>
              {UTILITY_LINKS.map(({ key, to, icon: Icon, testId }) => (
                <Link
                  key={testId}
                  to={to}
                  data-testid={testId}
                  aria-label={t(key)}
                  className="inline-flex h-9 w-9 items-center justify-center text-foreground transition-colors hover:text-primary"
                >
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </Link>
              ))}
              <LanguageSelector />
            </div>
          </div>
        </div>
        <SecondaryNav />
      </header>
      <SearchOverlay
        open={overlay.open}
        initialDept={overlay.dept}
        onClose={() => setOverlay({ open: false, dept: null })}
      />
    </>
  );
}
