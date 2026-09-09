const img = (id, w = 800) =>
  `https://images.unsplash.com/photo-${id}?crop=entropy&cs=srgb&fm=jpg&q=80&w=${w}&fit=crop`;

export const HERO_IMAGE = img("1772714601002-fbb0fea8a911", 1800);

export const DEPARTMENTS = [
  {
    id: "dept-muslimah",
    slug: "women-muslimah",
    names: { en: "Women Muslimah", id: "Busana Muslimah", uz: "Muslima ayollar", ru: "Женская мусульманская" },
    image: img("1762376268273-645db555eaf9", 900),
  },
  {
    id: "dept-uniqlo",
    slug: "uniqlo-products",
    names: { en: "UNIQLO Products", id: "Produk UNIQLO", uz: "UNIQLO mahsulotlari", ru: "Товары UNIQLO" },
    image: img("1603400521630-9f2de124b33b", 900),
  },
  {
    id: "dept-skincare",
    slug: "tropical-halal-skincare",
    names: { en: "Tropical Halal Skincare", id: "Skincare Halal Tropis", uz: "Tropik halol teri parvarishi", ru: "Тропический халяль-уход" },
    image: img("1616750819456-5cdee9b85d22", 900),
  },
];

export const CATEGORIES = [
  { id: "c-hijab", slug: "hijab", departmentId: "dept-muslimah", names: { en: "Hijab", id: "Hijab / Kerudung", uz: "Hijob", ru: "Хиджаб" }, image: img("1550546094-9835463f9f71") },
  { id: "c-gamis", slug: "gamis", departmentId: "dept-muslimah", names: { en: "Gamis Dress", id: "Gamis", uz: "Gamis", ru: "Гамис" }, image: img("1779400882805-5d304490a5de") },
  { id: "c-abaya", slug: "abaya", departmentId: "dept-muslimah", names: { en: "Abaya", id: "Abaya", uz: "Abaya", ru: "Абая" }, image: img("1762605135321-d025ebbd13d8") },
  { id: "c-tunik", slug: "tunik", departmentId: "dept-muslimah", names: { en: "Tunic", id: "Tunik", uz: "Tunika", ru: "Туника" }, image: img("1728485292065-bccf7eab3287") },
  { id: "c-blouse", slug: "blouse-muslimah", departmentId: "dept-muslimah", names: { en: "Muslimah Blouse", id: "Blouse Muslimah", uz: "Muslima bluzkasi", ru: "Мусульманская блуза" }, image: img("1574297500578-afae55026ff3") },
  { id: "c-rok", slug: "rok-muslimah", departmentId: "dept-muslimah", names: { en: "Muslimah Skirt", id: "Rok Muslimah", uz: "Muslima yubkasi", ru: "Мусульманская юбка" }, image: img("1552874869-5c39ec9288dc") },
  { id: "c-outerwear", slug: "outerwear", departmentId: "dept-uniqlo", names: { en: "Outerwear", id: "Outerwear", uz: "Ustki kiyimlar", ru: "Верхняя одежда" }, image: img("1618244965061-1d27b208d6e8") },
  { id: "c-hoodies", slug: "sweatshirts-hoodies", departmentId: "dept-uniqlo", names: { en: "Sweatshirts & Hoodies", id: "Sweatshirt & Hoodie", uz: "Svitshotlar va xudilar", ru: "Свитшоты и худи" }, image: img("1504198458649-3128b932f49e") },
  { id: "c-tshirts", slug: "tshirts-sweats", departmentId: "dept-uniqlo", names: { en: "T-Shirts & Sweats", id: "Kaos & Sweat", uz: "Futbolkalar", ru: "Футболки" }, image: img("1619032468883-89a84f565cba") },
  { id: "c-bottoms", slug: "bottoms", departmentId: "dept-uniqlo", names: { en: "Bottoms", id: "Bawahan", uz: "Shimlar", ru: "Низ" }, image: img("1699797467199-6bdf301649e8") },
  { id: "c-shirts", slug: "shirts-blouses", departmentId: "dept-uniqlo", names: { en: "Shirts & Blouses", id: "Kemeja & Blus", uz: "Ko'ylak va bluzkalar", ru: "Рубашки и блузы" }, image: img("1604506847073-4a8e18e07d92") },
  { id: "c-knitwear", slug: "sweaters-knitwear", departmentId: "dept-uniqlo", names: { en: "Sweaters & Knitwear", id: "Sweater & Rajutan", uz: "Sviterlar va trikotaj", ru: "Свитеры и трикотаж" }, image: img("1641642231157-0849081598a2") },
  { id: "c-facial-wash", slug: "facial-wash", departmentId: "dept-skincare", names: { en: "Facial Wash", id: "Sabun Wajah", uz: "Yuz yuvish vositasi", ru: "Средство для умывания" }, image: img("1620916566398-39f1143ab7be") },
  { id: "c-moist-cream", slug: "moist-cream", departmentId: "dept-skincare", names: { en: "Moist Cream", id: "Krim Pelembap", uz: "Namlovchi krem", ru: "Увлажняющий крем" }, image: img("1670201202833-b0932731628f") },
  { id: "c-sunscreen", slug: "sunscreen", departmentId: "dept-skincare", names: { en: "Sunscreen", id: "Tabir Surya", uz: "Quyoshdan himoya", ru: "Солнцезащитный крем" }, image: img("1616750819456-5cdee9b85d22") },
  { id: "c-serum", slug: "serum", departmentId: "dept-skincare", names: { en: "Serum", id: "Serum", uz: "Syvorotka", ru: "Сыворотка" }, image: img("1613803745799-ba6c10aace85") },
  { id: "c-face-mist", slug: "face-mist", departmentId: "dept-skincare", names: { en: "Face Mist", id: "Face Mist", uz: "Yuz spreyi", ru: "Мист для лица" }, image: img("1616750819456-5cdee9b85d22") },
];

export const DEMO_PRODUCTS = [
  { id: "p1", name: "Gray Sweat Oversized Full-Zip Hoodie", price: 499000, compareAt: null, image: img("1564557287817-3785e38ec1f5"), colors: ["#8A8A8A", "#1A1A1A", "#D9C7A7", "#22304A"], meta: "UNISEX, XS–XXL", badge: "new" },
  { id: "p2", name: "Essential Oversized Hoodie", price: 479000, compareAt: null, image: img("1542406775-ade58c52d2e4"), colors: ["#F5F5F5", "#8A8A8A", "#1A1A1A"], meta: "UNISEX, XS–XXL", badge: null },
  { id: "p3", name: "Premium Chiffon Hijab", price: 89000, compareAt: null, image: img("1550546094-9835463f9f71"), colors: ["#1A1A1A", "#7A2E3A", "#D9C7A7", "#22304A", "#6B6B4E"], meta: "WOMEN, 180×70 CM", badge: null },
  { id: "p4", name: "Gamis A-Line Dress", price: 389000, compareAt: 459000, image: img("1779400882805-5d304490a5de"), colors: ["#B98BA7", "#D9C7A7"], meta: "WOMEN, S–XL", badge: "sale" },
  { id: "p5", name: "Abaya Classic Black", price: 549000, compareAt: null, image: img("1762605135321-d025ebbd13d8"), colors: ["#1A1A1A"], meta: "WOMEN, S–XXL", badge: null },
  { id: "p6", name: "Tunik Linen Relaxed", price: 299000, compareAt: null, image: img("1728485292065-bccf7eab3287"), colors: ["#D9C7A7", "#6B6B4E", "#F5F5F5"], meta: "WOMEN, XS–XL", badge: "new" },
  { id: "p7", name: "Halal Gentle Facial Wash 100ml", price: 79000, compareAt: null, image: img("1620916566398-39f1143ab7be"), colors: [], meta: "SKINCARE, 100 ML", badge: null },
  { id: "p8", name: "Brightening Serum 30ml", price: 149000, compareAt: 189000, image: img("1613803745799-ba6c10aace85"), colors: [], meta: "SKINCARE, 30 ML", badge: "sale" },
  { id: "p9", name: "Tropical Moist Cream 50ml", price: 129000, compareAt: null, image: img("1670201202833-b0932731628f"), colors: [], meta: "SKINCARE, 50 ML", badge: null },
  { id: "p10", name: "Wool Blend Outer Parka", price: 899000, compareAt: null, image: img("1618244965061-1d27b208d6e8"), colors: ["#6B6B4E", "#1A1A1A"], meta: "UNISEX, XS–XL", badge: "new" },
];

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

export const localizedName = (obj, locale) =>
  obj.names[locale] ?? obj.names.en;

export const localizedField = (obj, field, locale) =>
  obj[field]?.[locale] ?? obj[field]?.en ?? "";
