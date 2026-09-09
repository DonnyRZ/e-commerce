const img = (id, w = 800) =>
  `https://images.unsplash.com/photo-${id}?crop=entropy&cs=srgb&fm=jpg&q=80&w=${w}&fit=crop`;

export const HERO_IMAGE = img("1772714601002-fbb0fea8a911", 1800);

export const EDITORIALS = [
  {
    id: "e1",
    slug: "modest-styling-guide",
    image: img("1552874869-5c39ec9288dc", 900),
    labels: { en: "Guide", id: "Panduan", uz: "Qo'llanma", ru: "Гид" },
    titles: { en: "Modest Styling Guide", id: "Panduan Gaya Muslimah", uz: "Muslimona uslub qo'llanmasi", ru: "Гид по скромному стилю" },
    descriptions: {
      en: "Simple ways to build an elegant modest wardrobe for every day.",
      id: "Cara sederhana membangun lemari pakaian muslimah yang elegan untuk setiap hari.",
      uz: "Har kun uchun nafis muslimona garderob yaratishning oddiy usullari.",
      ru: "Простые способы собрать элегантный скромный гардероб на каждый день.",
    },
  },
  {
    id: "e2",
    slug: "hijab-styling-guide",
    image: img("1536528947088-d655e462f4d3", 900),
    labels: { en: "Guide", id: "Panduan", uz: "Qo'llanma", ru: "Гид" },
    titles: { en: "Hijab Styling Guide", id: "Panduan Gaya Hijab", uz: "Hijob qo'llanmasi", ru: "Гид по стилю хиджаба" },
    descriptions: {
      en: "From chiffon to jersey — find your perfect drape and color pairings.",
      id: "Dari sifon hingga jersey — temukan jatuh kain dan padanan warna terbaikmu.",
      uz: "Shifondan jerseygacha — mukammal mato va rang uyg'unligini toping.",
      ru: "От шифона до джерси — подберите идеальную драпировку и сочетание цветов.",
    },
  },
  {
    id: "e3",
    slug: "tropical-halal-skincare-routine",
    image: img("1670201202833-b0932731628f", 900),
    labels: { en: "Routine", id: "Rutinitas", uz: "Tartib", ru: "Ритуал" },
    titles: { en: "Tropical Halal Skincare Routine", id: "Rutinitas Skincare Halal Tropis", uz: "Tropik halol teri parvarishi tartibi", ru: "Тропический халяль-уход: ритуал" },
    descriptions: {
      en: "A gentle halal routine made for warm, humid climates.",
      id: "Rutinitas halal yang lembut untuk iklim hangat dan lembap.",
      uz: "Iliq va nam iqlim uchun mo'rt halol parvarish tartibi.",
      ru: "Мягкий халяль-ритуал для тёплого влажного климата.",
    },
  },
  {
    id: "e4",
    slug: "new-season-muslimah-edit",
    image: img("1763906802942-8b1959ad0698", 900),
    labels: { en: "Edit", id: "Pilihan", uz: "Tanlov", ru: "Подборка" },
    titles: { en: "New Season Muslimah Edit", id: "Pilihan Muslimah Musim Baru", uz: "Yangi mavsum muslima tanlovi", ru: "Мусульманская подборка нового сезона" },
    descriptions: {
      en: "Flowing gamis, clean abayas, soft neutrals — this season's key silhouettes.",
      id: "Gamis mengalir, abaya bersih, warna netral lembut — siluet utama musim ini.",
      uz: "Oqimli gamislar, toza abayalar, yumshoq neytral ranglar — shu mavsumning asosiy siluetlari.",
      ru: "Струящиеся гамисы, лаконичные абаи, мягкие нейтральные тона — ключевые силуэты сезона.",
    },
  },
];

export const localizedField = (obj, field, locale) =>
  obj[field]?.[locale] ?? obj[field]?.en ?? "";
