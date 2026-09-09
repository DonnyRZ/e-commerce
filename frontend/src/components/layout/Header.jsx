import { Link } from "react-router-dom";
import { Heart, Search, ShoppingBag, User } from "lucide-react";
import { useI18n } from "@/i18n";
import LanguageSelector from "./LanguageSelector";
import MobileNavigation from "./MobileNavigation";

const NAV_ITEMS = [
  { key: "nav.home", to: "/" },
  { key: "nav.womenMuslimah", to: "/" },
  { key: "nav.apparel", to: "/" },
  { key: "nav.skincare", to: "/" },
];

const ENTRY_ITEMS = [
  { key: "header.searchPlaceholder", to: "/search", icon: Search, testId: "search-entry" },
  { key: "header.wishlist", to: "/wishlist", icon: Heart, testId: "wishlist-entry" },
  { key: "header.cart", to: "/cart", icon: ShoppingBag, testId: "cart-entry" },
  { key: "header.account", to: "/account", icon: User, testId: "account-entry" },
];

export default function Header() {
  const { t } = useI18n();
  return (
    <header
      data-testid="site-header"
      className="sticky top-0 z-40 border-b border-border bg-background"
    >
      <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center gap-2 px-4 sm:px-6 lg:h-16 lg:gap-4 lg:px-10">
        <MobileNavigation />
        <Link
          to="/"
          data-testid="brand-logo"
          className="text-sm font-bold tracking-widest sm:text-base"
        >
          {t("brand.name")}
        </Link>
        <nav
          className="ml-6 hidden items-center gap-6 lg:flex"
          aria-label="Primary"
          data-testid="desktop-nav"
        >
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.key}
              to={item.to}
              data-testid={`nav-${item.key.split(".")[1]}`}
              className="text-sm font-medium text-foreground transition-colors hover:text-primary"
            >
              {t(item.key)}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-0.5 sm:gap-1">
          <LanguageSelector />
          {ENTRY_ITEMS.map(({ key, to, icon: Icon, testId }) => (
            <Link
              key={testId}
              to={to}
              data-testid={testId}
              aria-label={t(key)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md text-foreground transition-colors hover:bg-secondary hover:text-primary"
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
            </Link>
          ))}
        </div>
      </div>
    </header>
  );
}
