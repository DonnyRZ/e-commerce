import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCategories, getDepartments } from "@/lib/api";
import { pickLocalized, toCardCategory } from "@/lib/localize";
import CategoryCard from "@/components/common/CategoryCard";

export default function SearchOverlay({ open, initialDept, onClose }) {
  const { locale, t } = useI18n();
  const navigate = useNavigate();
  const [dept, setDept] = useState(initialDept || null);
  const [query, setQuery] = useState("");

  const { data: departments = [] } = useQuery({
    queryKey: ["departments"],
    queryFn: getDepartments,
    staleTime: 5 * 60 * 1000,
  });
  const { data: allCategories = [] } = useQuery({
    queryKey: ["categories", "all"],
    queryFn: () => getCategories(),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (open) {
      setDept(initialDept || null);
      setQuery("");
    }
  }, [open, initialDept]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  const activeDept = dept || departments[0]?.slug;
  const cats = allCategories.filter((c) => c.department === activeDept);

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
      className="fixed inset-0 z-50 flex flex-col bg-background"
    >
      <div className="border-b border-border">
        <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center justify-between px-4 sm:px-6 lg:h-16 lg:px-10">
          <Link
            to="/"
            onClick={onClose}
            className="text-sm font-extrabold tracking-widest sm:text-base"
          >
            {t("brand.name")}
          </Link>
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
          <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-6">
            {cats.map((c) => (
              <CategoryCard
                key={c.id}
                category={toCardCategory(c, locale)}
                name={toCardCategory(c, locale).name}
                onNavigate={onClose}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
