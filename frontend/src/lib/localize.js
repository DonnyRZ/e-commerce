export const pickLocalized = (translations, locale, field = "title") =>
  translations?.[locale]?.[field] ?? translations?.en?.[field] ?? "";

const COLOR_HEX = {
  gray: "#8A8A8A",
  black: "#1A1A1A",
  beige: "#D9C7A7",
  navy: "#22304A",
  "off white": "#F5F1E8",
  white: "#FFFFFF",
  maroon: "#7A2E3A",
  "dusty purple": "#B98BA7",
  "dusty pink": "#E8C4C4",
};

export const colorHex = (name) =>
  COLOR_HEX[String(name).toLowerCase()] || "#C9C9C9";

export function toCardProduct(p, locale) {
  return {
    id: p.id,
    slug: p.slug,
    name: pickLocalized(p.translations, locale),
    image: p.media?.[0]?.url || "",
    price: p.base_price,
    compareAt: p.compare_at_price,
    colors: (p.colors || []).map(colorHex),
    meta: (p.brand || "").toUpperCase(),
    badge: p.compare_at_price ? "sale" : p.new_arrival ? "new" : null,
    stockState: p.stock_state,
    href: `/product/${p.slug}`,
  };
}

export function toCardCategory(c, locale) {
  return {
    slug: c.slug,
    image: c.image_url || "",
    name: pickLocalized(c.translations, locale),
  };
}
