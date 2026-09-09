import { useState } from "react";
import { useI18n } from "@/i18n";
import { colorHex } from "@/lib/localize";

export default function FilterPanel({ meta, params, setParam, clearAll }) {
  const { t } = useI18n();
  const [minPrice, setMinPrice] = useState(params.min_price || "");
  const [maxPrice, setMaxPrice] = useState(params.max_price || "");

  const hasActive =
    params.min_price || params.max_price || params.color || params.size || params.availability;

  return (
    <div data-testid="filter-panel" className="space-y-7">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("plp.filters")}</h3>
        {hasActive ? (
          <button
            type="button"
            data-testid="filter-clear"
            onClick={clearAll}
            className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            {t("plp.clearFilters")}
          </button>
        ) : null}
      </div>

      {meta?.price ? (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("plp.price")}
          </p>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min="0"
              data-testid="filter-price-min"
              value={minPrice}
              onChange={(e) => setMinPrice(e.target.value)}
              placeholder={t("plp.minPrice")}
              className="h-9 w-full border border-border bg-background px-2 text-sm outline-none focus:border-foreground"
            />
            <span className="text-muted-foreground">–</span>
            <input
              type="number"
              min="0"
              data-testid="filter-price-max"
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)}
              placeholder={t("plp.maxPrice")}
              className="h-9 w-full border border-border bg-background px-2 text-sm outline-none focus:border-foreground"
            />
          </div>
          <button
            type="button"
            data-testid="filter-price-apply"
            onClick={() => {
              setParam("min_price", minPrice);
              setParam("max_price", maxPrice);
            }}
            className="mt-2 w-full border border-foreground py-1.5 text-xs font-medium transition-colors hover:bg-foreground hover:text-background"
          >
            {t("plp.apply")}
          </button>
        </div>
      ) : null}

      {meta?.colors?.length ? (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("plp.color")}
          </p>
          <div className="flex flex-wrap gap-2">
            {meta.colors.map((color) => (
              <button
                key={color}
                type="button"
                data-testid={`filter-color-${color.toLowerCase().replace(/\s+/g, "-")}`}
                aria-label={color}
                aria-pressed={params.color === color}
                onClick={() => setParam("color", params.color === color ? "" : color)}
                className={`h-7 w-7 rounded-full border-2 transition-colors ${
                  params.color === color
                    ? "border-primary"
                    : "border-border hover:border-foreground"
                }`}
                style={{ backgroundColor: colorHex(color) }}
              />
            ))}
          </div>
        </div>
      ) : null}

      {meta?.sizes?.length ? (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("plp.size")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {meta.sizes.map((size) => (
              <button
                key={size}
                type="button"
                data-testid={`filter-size-${size.toLowerCase()}`}
                aria-pressed={params.size === size}
                onClick={() => setParam("size", params.size === size ? "" : size)}
                className={`border px-2.5 py-1 text-xs font-medium transition-colors ${
                  params.size === size
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border hover:border-foreground"
                }`}
              >
                {size}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("plp.availability")}
        </p>
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            data-testid="filter-in-stock"
            checked={params.availability === "in_stock"}
            onChange={(e) =>
              setParam("availability", e.target.checked ? "in_stock" : "")
            }
            className="h-4 w-4 accent-primary"
          />
          {t("plp.inStock")}
        </label>
      </div>
    </div>
  );
}
