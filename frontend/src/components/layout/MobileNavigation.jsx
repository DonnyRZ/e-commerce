import { Link } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { LOCALE_LABELS, SUPPORTED_LOCALES, useI18n } from "@/i18n";
import { getCatalogTree } from "@/lib/api";
import { pickLocalized } from "@/lib/localize";
import { taxonomyLabel } from "@/lib/taxonomy";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import BrandLogo from "@/components/brand/BrandLogo";
import { useAuth } from "@/lib/AuthContext";

const QUICK_LINKS = [
  { key: "nav.newArrivals", to: "/shop?badge=new" },
  { key: "nav.bestSellers", to: "/shop?badge=bestseller" },
  { key: "nav.sale", to: "/shop?badge=sale" },
];

const ACCOUNT_LINKS = [
  { key: "header.searchPlaceholder", to: "/search" },
  { key: "header.wishlist", to: "/wishlist" },
  { key: "header.cart", to: "/cart" },
  { key: "header.account", to: "/account" },
];

export default function MobileNavigation() {
  const { locale, setLocale, t } = useI18n();
  const { user } = useAuth();
  const { data: catalogTree = [] } = useQuery({
    queryKey: ["catalog-tree"],
    queryFn: getCatalogTree,
    staleTime: 5 * 60 * 1000,
  });
  const accountLinks = ACCOUNT_LINKS.map((item) =>
    item.key === "header.account"
      ? { ...item, to: user?.role === "customer" ? "/account" : "/login" }
      : item
  );

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          data-testid="mobile-menu-button"
          aria-label={t("header.openMenu")}
          className="lg:hidden"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72 overflow-y-auto p-0" data-testid="mobile-menu">
        <SheetTitle className="sr-only">{t("brand.name")}</SheetTitle>
        <div className="flex items-center justify-between border-b px-4 py-3">
          <BrandLogo size="sm" to="/" testId="mobile-brand-logo" priority />
          <SheetClose asChild>
            <Button
              variant="ghost"
              size="icon"
              data-testid="mobile-menu-close"
              aria-label={t("header.closeMenu")}
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </Button>
          </SheetClose>
        </div>
        <nav className="flex flex-col px-4 py-2" aria-label="Departments">
          {catalogTree.map((dept) => (
            <div key={dept.id} className="border-b border-border py-2" data-testid={`mobile-nav-group-${dept.slug}`}>
              <SheetClose asChild>
                <Link
                  to={`/shop?department=${dept.slug}`}
                  data-testid={`mobile-nav-${dept.slug}`}
                  className="block py-2 text-sm font-semibold hover:text-primary"
                >
                  {taxonomyLabel(dept, locale, pickLocalized)}
                </Link>
              </SheetClose>
              {(dept.children || []).length ? (
                <div className="pb-1 pl-3">
                  {dept.children.map((category) => (
                    <SheetClose asChild key={category.id}>
                      <Link
                        to={`/shop?category=${category.slug}`}
                        data-testid={`mobile-nav-category-${category.slug}`}
                        className="block py-1.5 text-sm text-muted-foreground hover:text-primary"
                      >
                        {taxonomyLabel(category, locale, pickLocalized)}
                      </Link>
                    </SheetClose>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </nav>
        <nav className="flex flex-col px-4 py-2" aria-label="Quick links">
          {QUICK_LINKS.map((item) => (
            <SheetClose asChild key={item.key}>
              <Link
                to={item.to}
                data-testid={`mobile-nav-${item.key.split(".")[1]}`}
                className="border-b border-border py-3 text-sm font-medium text-muted-foreground hover:text-primary"
              >
                {t(item.key)}
              </Link>
            </SheetClose>
          ))}
        </nav>
        <nav className="flex flex-col px-4 py-2" aria-label="Account">
          {accountLinks.map((item) => (
            <SheetClose asChild key={item.key}>
              <Link
                to={item.to}
                data-testid={`mobile-nav-${item.key.split(".")[1]}`}
                className="border-b border-border py-3 text-sm font-medium text-muted-foreground hover:text-primary"
              >
                {t(item.key)}
              </Link>
            </SheetClose>
          ))}
        </nav>
        <div className="px-4 py-4">
          <p className="mb-2 text-xs uppercase text-muted-foreground">
            {t("header.language")}
          </p>
          <div className="flex flex-col gap-1">
            {SUPPORTED_LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                data-testid={`mobile-language-option-${code}`}
                onClick={() => setLocale(code)}
                className={`py-2 text-left text-sm ${
                  code === locale ? "font-semibold text-primary" : ""
                }`}
              >
                {LOCALE_LABELS[code]}
              </button>
            ))}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
