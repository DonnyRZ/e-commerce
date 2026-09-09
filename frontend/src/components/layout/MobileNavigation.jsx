import { Link } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { LOCALE_LABELS, SUPPORTED_LOCALES, useI18n } from "@/i18n";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

const NAV_KEYS = ["nav.home", "nav.womenMuslimah", "nav.apparel", "nav.skincare"];

export default function MobileNavigation() {
  const { locale, setLocale, t } = useI18n();
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
      <SheetContent side="left" className="w-72 p-0" data-testid="mobile-menu">
        <SheetTitle className="sr-only">{t("brand.name")}</SheetTitle>
        <div className="flex items-center justify-between border-b px-4 py-3">
          <span className="text-sm font-bold tracking-wide">{t("brand.name")}</span>
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
        <nav className="flex flex-col px-4 py-2" aria-label="Mobile">
          {NAV_KEYS.map((key) => (
            <SheetClose asChild key={key}>
              <Link
                to="/"
                data-testid={`mobile-nav-${key.split(".")[1]}`}
                className="border-b border-border py-3 text-sm font-medium hover:text-primary"
              >
                {t(key)}
              </Link>
            </SheetClose>
          ))}
        </nav>
        <div className="px-4 pt-4">
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
