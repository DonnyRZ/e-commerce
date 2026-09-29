import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Heart, Search, ShoppingBag, User } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCatalogTree } from "@/lib/api";
import { useShop } from "@/lib/ShopContext";
import { useAuth } from "@/lib/AuthContext";
import { pickLocalized } from "@/lib/localize";
import { taxonomyLabel, taxonomySections } from "@/lib/taxonomy";
import LanguageSelector from "./LanguageSelector";
import MobileNavigation from "./MobileNavigation";
import SearchOverlay from "./SearchOverlay";
import BrandLogo from "@/components/brand/BrandLogo";

const UTILITY_LINKS = [
  { key: "header.wishlist", to: "/wishlist", icon: Heart, testId: "wishlist-entry" },
  { key: "header.account", to: "/account", icon: User, testId: "account-entry" },
  { key: "header.cart", to: "/cart", icon: ShoppingBag, testId: "cart-entry" },
];

export default function Header() {
  const { locale, t } = useI18n();
  const { cartCount, wishlistCount } = useShop();
  const { user } = useAuth();
  const [overlay, setOverlay] = useState({ open: false, dept: null });
  const [headerVisible, setHeaderVisible] = useState(true);
  const lastScrollY = useRef(0);
  const scrollDirection = useRef(null);
  const scrollDistance = useRef(0);
  const { data: catalogTree = [] } = useQuery({
    queryKey: ["catalog-tree"],
    queryFn: getCatalogTree,
    staleTime: 5 * 60 * 1000,
  });
  const counts = { "cart-entry": cartCount, "wishlist-entry": wishlistCount };
  const utilityLinks = UTILITY_LINKS.map((item) =>
    item.testId === "account-entry"
      ? { ...item, to: user?.role === "customer" ? "/account" : "/login" }
      : item
  );

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      const previousScrollY = lastScrollY.current;
      const scrollDelta = currentScrollY - previousScrollY;

      if (currentScrollY <= 8) {
        scrollDirection.current = null;
        scrollDistance.current = 0;
        setHeaderVisible(true);
      } else if (scrollDelta !== 0) {
        const nextDirection = scrollDelta > 0 ? "down" : "up";
        if (scrollDirection.current !== nextDirection) {
          scrollDirection.current = nextDirection;
          scrollDistance.current = Math.abs(scrollDelta);
        } else {
          scrollDistance.current += Math.abs(scrollDelta);
        }

        if (nextDirection === "down" && scrollDistance.current >= 16) {
          setHeaderVisible(false);
        } else if (nextDirection === "up" && scrollDistance.current >= 12) {
          setHeaderVisible(true);
        }
      }

      lastScrollY.current = currentScrollY;
    };

    lastScrollY.current = window.scrollY;
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <>
      <header
        data-testid="site-header"
        className={`sticky top-0 z-40 bg-background transition-transform duration-200 will-change-transform ${
          headerVisible ? "translate-y-0" : "-translate-y-full"
        }`}
      >
        <div className="border-b border-border">
          <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center gap-2 px-4 sm:px-6 lg:h-16 lg:gap-4 lg:px-10">
            <MobileNavigation />
            <BrandLogo size="md" to="/" testId="brand-logo" priority />
            <nav
              className="ml-6 hidden items-center gap-7 lg:flex"
              aria-label="Primary"
              data-testid="desktop-nav"
            >
              {catalogTree.map((dept) => (
                <div key={dept.id} className="group relative">
                  <Link
                    to={`/shop?department=${dept.slug}`}
                    data-testid={`nav-${dept.slug}`}
                    className="inline-flex items-center py-5 text-sm font-semibold tracking-wide text-foreground transition-colors hover:text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    {taxonomyLabel(dept, locale, pickLocalized)}
                  </Link>
                  {(dept.children || []).length ? (
                    <div
                      className="invisible absolute left-1/2 top-full z-50 w-[min(560px,calc(100vw-2rem))] -translate-x-1/2 border border-border bg-background p-5 opacity-0 shadow-xl transition-[opacity,visibility] duration-150 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
                      data-testid={`nav-menu-${dept.slug}`}
                    >
                      <div className="grid gap-5 sm:grid-cols-2">
                        {taxonomySections(dept).map(({ items }) => (
                          <div key={`${dept.id}-categories`}>
                            <div className="flex flex-col gap-1">
                              {items.map((category) => (
                                <Link
                                  key={category.id}
                                  to={`/shop?category=${category.slug}`}
                                  data-testid={`nav-category-${category.slug}`}
                                  className="text-sm text-muted-foreground transition-colors hover:text-foreground hover:underline"
                                >
                                  {taxonomyLabel(category, locale, pickLocalized)}
                                </Link>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-0.5">
              <button
                type="button"
                data-testid="search-entry"
                aria-label={t("header.searchPlaceholder")}
                onClick={() => setOverlay({ open: true, dept: null })}
              className="inline-flex h-11 w-11 items-center justify-center text-foreground transition-colors hover:text-primary"
              >
                <Search className="h-5 w-5" aria-hidden="true" />
              </button>
              {utilityLinks.map(({ key, to, icon: Icon, testId }) => (
                <Link
                  key={testId}
                  to={to}
                  data-testid={testId}
                  aria-label={t(key)}
                  className={`relative ${testId === "cart-entry" ? "inline-flex" : "hidden sm:inline-flex"} h-11 w-11 items-center justify-center text-foreground transition-colors hover:text-primary`}
                >
                  <Icon className="h-5 w-5" aria-hidden="true" />
                  {counts[testId] > 0 ? (
                    <span
                      data-testid={`${testId}-count`}
                      className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold leading-none text-primary-foreground"
                    >
                      {counts[testId]}
                    </span>
                  ) : null}
                </Link>
              ))}
              <span className="hidden sm:inline-flex">
                <LanguageSelector />
              </span>
            </div>
          </div>
        </div>
      </header>
      <SearchOverlay
        open={overlay.open}
        initialDept={overlay.dept}
        onClose={() => setOverlay({ open: false, dept: null })}
      />
    </>
  );
}
