export const CMS_LOCALES = ["en", "id", "uz", "ru"];

export const CMS_CONTENT_TYPES = [
  { value: "hero", label: "Hero utama" },
  { value: "announcement", label: "Pengumuman" },
  { value: "banner", label: "Banner promosi" },
  { value: "story", label: "Cerita & editorial" },
  { value: "page", label: "Halaman informasi" },
  { value: "faq_item", label: "Tanya jawab" },
  { value: "nav_item", label: "Navigasi sekunder" },
  { value: "footer_group", label: "Grup footer" },
  { value: "footer_item", label: "Tautan footer" },
  { value: "footer_text", label: "Teks footer / homepage" },
  { value: "homepage_section", label: "Bagian homepage" },
  { value: "department_visual", label: "Visual departemen" },
];

export const CMS_PRODUCT_SECTION_KEYS = [
  "best_sellers",
  "new_arrivals",
  "skincare",
  "daily_style",
];

export const CMS_LEGACY_SECTION_KEYS = ["curated_primary", "curated_secondary"];

export const CMS_SECTION_KEYS = [
  "promo_bar", "hero", "categories", "departments",
  ...CMS_PRODUCT_SECTION_KEYS,
  "stories", "footer",
];

export const CMS_VALID_SECTION_KEYS = [
  ...CMS_SECTION_KEYS,
  ...CMS_LEGACY_SECTION_KEYS,
];

export const CMS_SECTION_LABELS = {
  promo_bar: "Bar pengumuman",
  hero: "Hero utama",
  categories: "Department",
  departments: "Department",
  best_sellers: "Terlaris",
  new_arrivals: "Koleksi Terbaru",
  skincare: "Rawat Kulitmu",
  daily_style: "Gaya Sehari-hari",
  stories: "Stories",
  footer: "Footer",
  curated_primary: "Section lama",
  curated_secondary: "Section lama",
};

export const CMS_TRANSLATION_FIELDS = {
  hero: ["eyebrow", "title", "subtitle", "description", "cta_label", "secondary_cta_label", "alt_text"],
  announcement: ["title"],
  banner: ["eyebrow", "title", "subtitle", "description", "cta_label", "alt_text"],
  story: ["eyebrow", "title", "description", "body", "cta_label", "alt_text"],
  page: ["title", "subtitle", "description", "body"],
  faq_item: ["title", "body"],
  nav_item: ["title"],
  footer_group: ["title"],
  footer_item: ["title"],
  footer_text: ["title", "description"],
  homepage_section: ["title"],
  department_visual: ["alt_text"],
};

export const CMS_MEDIA_TYPES = ["banner", "story", "page", "department_visual"];

export const cmsTypeLabel = (value) =>
  CMS_CONTENT_TYPES.find((type) => type.value === value)?.label || value?.replaceAll("_", " ") || "Konten";

export const cmsSectionLabel = (value) => CMS_SECTION_LABELS[value] || value?.replaceAll("_", " ") || "Bagian homepage";

export const cmsStatusLabel = (value) => ({
  draft: "Draft",
  published: "Tayang",
  archived: "Diarsipkan",
}[value] || value || "—");
