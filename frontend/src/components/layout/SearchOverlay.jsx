import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCatalogTree } from "@/lib/api";
import { pickLocalized, toCardCategory } from "@/lib/localize";
import { taxonomyLabel, taxonomySections } from "@/lib/taxonomy";
import CategoryCard from "@/components/common/CategoryCard";
import BrandLogo from "@/components/brand/BrandLogo";

export default function SearchOverlay({ open, initialDept, onClose }) {
  const { locale, t } = useI18n();
  const navigate = useNavigate();
  const [dept, setDept] = useState(initialDept || null);
  const [query, setQuery] = useState("");
  const dialogRef = useRef(null);
  const inputRef = useRef(null);
  const previousFocusRef = useRef(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  const { data: departments = [] } = useQuery({
    queryKey: ["catalog-tree"],
    queryFn: getCatalogTree,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!open) return undefined;
    previousFocusRef.current = document.activeElement;
    setDept(initialDept || null);
    setQuery("");
    const focusFrame = window.requestAnimationFrame(() => inputRef.current?.focus());
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previousFocusRef.current?.focus?.();
    };
  }, [open, initialDept]);

  if (!open) return null;

  const activeDept = dept || departments[0]?.slug;
  const activeRoot = departments.find((item) => item.slug === activeDept);
  const sections = taxonomySections(activeRoot);

  const submitSearch = (e) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    onClose();
    navigate(`/search?q=${encodeURIComponent(q)}`);
  };

  return (
    <div
      data-testid="search-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="search-overlay-title"
      ref={dialogRef}
      className="fixed inset-0 z-50 flex flex-col bg-background"
    >
      <div className="border-b border-border">
        <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center justify-between px-4 sm:px-6 lg:h-16 lg:px-10">
          <BrandLogo to="/" testId="search-brand-logo" size="sm" priority />
          <h1 id="search-overlay-title" className="sr-only">{t("header.searchPlaceholder")}</h1>
          <button
            type="button"
            data-testid="search-overlay-close"
            aria-label={t("common.close")}
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center text-foreground transition-colors hover:text-primary"
          >
            <X className="h-6 w-6" aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          <form onSubmit={submitSearch} className="relative">
            <input
              ref={inputRef}
              type="search"
              data-testid="search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("header.searchPlaceholder")}
              aria-label={t("header.searchPlaceholder")}
              className="h-12 w-full rounded-full border border-border bg-background pl-5 pr-12 text-sm outline-none focus:border-foreground"
            />
            <button
              type="submit"
              data-testid="search-submit"
              aria-label={t("header.searchPlaceholder")}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <Search className="h-5 w-5" aria-hidden="true" />
            </button>
          </form>
          <div
            className="mt-6 flex gap-6 overflow-x-auto border-b border-border"
            role="tablist"
            data-testid="search-dept-tabs"
          >
            {departments.map((d) => (
              <button
                key={d.id}
                type="button"
                role="tab"
                aria-selected={activeDept === d.slug}
                data-testid={`search-tab-${d.slug}`}
                onClick={() => setDept(d.slug)}
                className={`whitespace-nowrap pb-2.5 text-sm transition-colors ${
                  activeDept === d.slug
                    ? "border-b-2 border-foreground font-semibold text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {pickLocalized(d.translations, locale)}
              </button>
            ))}
          </div>
          <p className="mt-8 text-xs font-medium uppercase tracking-widest text-muted-foreground">
            {t("search.browseCategories")}
          </p>
          <div className="mt-4 space-y-8">
            {sections.map(({ group, items }) => (
              <section key={group?.id || items[0]?.id}>
                {group ? (
                  <Link
                    to={`/shop?category=${group.slug}`}
                    onClick={onClose}
                    className="text-xs font-semibold uppercase tracking-[0.16em] text-primary hover:underline"
                  >
                    {taxonomyLabel(group, locale, pickLocalized)}
                  </Link>
                ) : null}
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-6">
                  {items.map((category) => {
                    const card = toCardCategory(category, locale);
                    return (
                      <CategoryCard
                        key={category.id}
                        category={card}
                        name={card.name}
                        onNavigate={onClose}
                      />
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
