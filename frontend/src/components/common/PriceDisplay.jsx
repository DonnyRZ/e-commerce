import { useI18n, BASE_CURRENCY } from "@/i18n";

export const LOCALE_TAGS = { id: "id-ID", en: "en-US", uz: "uz-UZ", ru: "ru-RU" };

export default function PriceDisplay({
  amount,
  compareAt,
  currency = BASE_CURRENCY,
  className = "",
  "data-testid": dataTestId,
}) {
  const { locale } = useI18n();
  const tag = LOCALE_TAGS[locale] || "en-US";
  const format = (value) =>
    new Intl.NumberFormat(tag, {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
      maximumFractionDigits: 0,
    }).format(value);

  return (
    <span
      data-testid={dataTestId || "price-display"}
      className={`inline-flex max-w-full flex-wrap items-baseline gap-2 ${className}`}
    >
      <span className={compareAt ? "font-semibold text-primary" : "font-semibold"}>
        {format(amount)}
      </span>
      {compareAt ? (
        <s className="text-sm text-muted-foreground">{format(compareAt)}</s>
      ) : null}
    </span>
  );
}
