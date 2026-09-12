import fs from "node:fs";
import path from "node:path";

const products = [
  "gray-sweat-oversized-full-zip-hoodie",
  "essential-crewneck-sweatshirt",
  "wide-leg-relaxed-trousers",
  "premium-chiffon-hijab",
  "gamis-a-line-dress",
  "abaya-classic-black",
  "mukena-travel-set",
  "kids-muslimah-daily-set",
  "halal-gentle-facial-wash",
  "brightening-serum-30ml",
  "tropical-moist-cream-50ml",
  "halal-daily-sunscreen-spf50",
];
const variantPrefixes = [
  "GSOZH-GRY", "GSOZH-BLK", "GSOZH-BGE", "GSOZH-NVY",
  "ECSW-OWH", "ECSW-GRY", "ECSW-BLK", "WLRT-BLK", "WLRT-BGE",
  "PCH-BLK-VOL", "PCH-NVY-VOL", "PCH-BGE-CHF", "PCH-MRN-CHF",
  "GALD-DPL", "GALD-BGE", "ACBK-BLK", "MTS-WHT", "MTS-DPK",
];
const taxonomy = [
  ["department", "women-muslimah"], ["department", "uniqlo-products"],
  ["department", "tropical-halal-skincare"],
  ...[
    "hijab-kerudung", "gamis", "abaya", "tunik", "blouse-muslimah",
    "dress-muslimah", "setelan-muslimah", "outer-muslimah", "rok-muslimah",
    "celana-muslimah", "mukena", "busana-syari", "busana-muslimah-kerja",
    "busana-muslimah-pesta", "busana-muslimah-hamil-menyusui",
    "busana-muslimah-olahraga", "busana-muslimah-anak", "outerwear",
    "tshirts-sweats-fleece", "sweatshirts-hoodies", "bottoms", "shirts-blouses",
    "sweaters-knitwear", "dresses-skirts", "loungewear-home", "facial-wash",
    "moist-cream", "sunscreen", "serum", "face-mist",
  ].map((slug) => ["category", slug]),
];
const editorial = [
  ["hero", "home-hero"],
  ["editorial", "modest-styling-guide"],
  ["editorial", "hijab-styling-guide"],
  ["editorial", "tropical-halal-skincare-routine"],
  ["editorial", "new-season-muslimah-edit"],
];
const locales = { id: "", en: "", uz: "", ru: "" };
const alt = (label) => Object.fromEntries(Object.keys(locales).map((locale) => [locale, label]));
const entries = [];

for (const slug of products) {
  for (let index = 1; index <= 4; index += 1) {
    entries.push({
      asset_key: `product:${slug}:gallery:${index}`,
      filename: `product-${slug}-gallery-${index}.jpg`,
      entity_type: "product", entity_slug: slug, role: "gallery", sort_order: index - 1,
      locale_alt: alt(`${slug} product image ${index}`),
    });
  }
}
for (const prefix of variantPrefixes) {
  entries.push({
    asset_key: `variant:${prefix}`, filename: `variant-${prefix.toLowerCase()}.jpg`,
    entity_type: "variant", entity_sku_prefix: prefix, role: "variant", sort_order: 0,
    locale_alt: alt(`${prefix} color variant image`),
  });
}
for (const [entity_type, slug] of taxonomy) {
  entries.push({
    asset_key: `${entity_type}:${slug}`, filename: `${entity_type}-${slug}.jpg`,
    entity_type, entity_slug: slug, role: "taxonomy", sort_order: 0,
    locale_alt: alt(`${slug} collection image`),
  });
}
for (const [role, slug] of editorial) {
  entries.push({
    asset_key: `cms:${role}:${slug}`, filename: `${slug}.jpg`, entity_type: "cms",
    entity_slug: slug, role, sort_order: 0, locale_alt: alt(`${slug} editorial image`),
  });
}

const output = path.resolve("artifacts/imagegen/manifest.json");
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify({ version: 1, count: entries.length, entries }, null, 2)}\n`);
console.log(`wrote ${entries.length} entries to ${output}`);
