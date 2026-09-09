import { Link } from "react-router-dom";
import { useI18n } from "@/i18n";

const ITEMS = ["nav.newArrivals", "nav.bestSellers", "nav.sale"];

export default function SecondaryNav() {
  const { t } = useI18n();
  return (
    <nav data-testid="secondary-nav" className="border-b border-border">
      <div className="mx-auto flex w-full max-w-[1440px] items-center gap-6 overflow-x-auto px-4 sm:px-6 lg:justify-center lg:px-10">
        {ITEMS.map((key, i) => (
          <Link
            key={key}
            to="/shop"
            data-testid={`secondary-nav-${key.split(".")[1]}`}
            className={`whitespace-nowrap py-2.5 text-[13px] transition-colors ${
              i === 0
                ? "border-b-2 border-foreground font-semibold text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t(key)}
          </Link>
        ))}
      </div>
    </nav>
  );
}
