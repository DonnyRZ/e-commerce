import { Link } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { LOCALE_LABELS, SUPPORTED_LOCALES, useI18n } from "@/i18n";
import { getDepartments } from "@/lib/api";
import { pickLocalized } from "@/lib/localize";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

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
  const { data: departments = [] } = useQuery({
    queryKey: ["departments"],
    queryFn: getDepartments,
    staleTime: 5 * 60 * 1000,
  });

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
          <span className="text-sm font-extrabold tracking-widest">{t("brand.name")}</span>
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
          {departments.map((dept) => (
            <SheetClose asChild key={dept.id}>
              <Link
                to={`/shop?department=${dept.slug}`}
                data-testid={`mobile-nav-${dept.slug}`}
                className="border-b border-border py-3 text-sm font-semibold hover:text-primary"
              >
                {pickLocalized(dept.translations, locale)}
              </Link>
            </SheetClose>
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
          {ACCOUNT_LINKS.map((item) => (
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
