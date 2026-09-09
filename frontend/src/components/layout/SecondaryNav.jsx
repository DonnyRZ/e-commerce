import { Link, useSearchParams } from "react-router-dom";
import { useI18n } from "@/i18n";

const ITEMS = [
  { key: "nav.newArrivals", badge: "new" },
  { key: "nav.bestSellers", badge: "bestseller" },
  { key: "nav.sale", badge: "sale" },
];

export default function SecondaryNav() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const activeBadge = searchParams.get("badge");
  return (
    <nav data-testid="secondary-nav" className="border-b border-border">
      <div className="mx-auto flex w-full max-w-[1440px] items-center gap-6 overflow-x-auto px-4 sm:px-6 lg:justify-center lg:px-10">
        {ITEMS.map((item) => (
          <Link
            key={item.key}
            to={`/shop?badge=${item.badge}`}
            data-testid={`secondary-nav-${item.key.split(".")[1]}`}
            className={`whitespace-nowrap py-2.5 text-[13px] transition-colors ${
              activeBadge === item.badge
                ? "border-b-2 border-foreground font-semibold text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t(item.key)}
          </Link>
        ))}
      </div>
    </nav>
  );
}
