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
    image: img("1663573688938-2b3e7ea2ab33", 900),
  },
  {
    id: "dept-skincare",
    slug: "tropical-halal-skincare",
    names: { en: "Tropical Halal Skincare", id: "Skincare Halal Tropis", uz: "Tropik halol teri parvarishi", ru: "Тропический халяль-уход" },
    image: img("1616750819456-5cdee9b85d22", 900),
  },
];

export const CATEGORIES = [
  { id: "c-hijab", slug: "hijab", departmentId: "dept-muslimah", names: { en: "Hijab", id: "Hijab / Kerudung", uz: "Hijob", ru: "Хиджаб" }, image: img("1759150370507-87e833629a1a") },
  { id: "c-gamis", slug: "gamis", departmentId: "dept-muslimah", names: { en: "Gamis Dress", id: "Gamis", uz: "Gamis", ru: "Гамис" }, image: img("1761014219840-60329882ca51") },
  { id: "c-abaya", slug: "abaya", departmentId: "dept-muslimah", names: { en: "Abaya", id: "Abaya", uz: "Abaya", ru: "Абая" }, image: img("1718230800381-1b7ee3bfb2bd") },
  { id: "c-tunik", slug: "tunik", departmentId: "dept-muslimah", names: { en: "Tunic", id: "Tunik", uz: "Tunika", ru: "Туника" }, image: img("1728485292065-bccf7eab3287") },
  { id: "c-blouse", slug: "blouse-muslimah", departmentId: "dept-muslimah", names: { en: "Muslimah Blouse", id: "Blouse Muslimah", uz: "Muslima bluzkasi", ru: "Мусульманская блуза" }, image: img("1574297500578-afae55026ff3") },
  { id: "c-rok", slug: "rok-muslimah", departmentId: "dept-muslimah", names: { en: "Muslimah Skirt", id: "Rok Muslimah", uz: "Muslima yubkasi", ru: "Мусульманская юбка" }, image: img("1645088930126-f669feb0fc5f") },
  { id: "c-outerwear", slug: "outerwear", departmentId: "dept-uniqlo", names: { en: "Outerwear", id: "Outerwear", uz: "Ustki kiyimlar", ru: "Верхняя одежда" }, image: img("1618244965061-1d27b208d6e8") },
  { id: "c-hoodies", slug: "sweatshirts-hoodies", departmentId: "dept-uniqlo", names: { en: "Sweatshirts & Hoodies", id: "Sweatshirt & Hoodie", uz: "Svitshotlar va xudilar", ru: "Свитшоты и худи" }, image: img("1564557287817-3785e38ec1f5") },
  { id: "c-tshirts", slug: "tshirts-sweats", departmentId: "dept-uniqlo", names: { en: "T-Shirts & Sweats", id: "Kaos & Sweat", uz: "Futbolkalar", ru: "Футболки" }, image: img("1542406775-ade58c52d2e4") },
  { id: "c-bottoms", slug: "bottoms", departmentId: "dept-uniqlo", names: { en: "Bottoms", id: "Bawahan", uz: "Shimlar", ru: "Низ" }, image: img("1688111421205-a0a85415b224") },
  { id: "c-shirts", slug: "shirts-blouses", departmentId: "dept-uniqlo", names: { en: "Shirts & Blouses", id: "Kemeja & Blus", uz: "Ko'ylak va bluzkalar", ru: "Рубашки и блузы" }, image: img("1620916566398-39f1143ab7be") },
  { id: "c-knitwear", slug: "sweaters-knitwear", departmentId: "dept-uniqlo", names: { en: "Sweaters & Knitwear", id: "Sweater & Rajutan", uz: "Sviterlar va trikotaj", ru: "Свитеры и трикотаж" }, image: img("1670201202833-b0932731628f") },
  { id: "c-facial-wash", slug: "facial-wash", departmentId: "dept-skincare", names: { en: "Facial Wash", id: "Sabun Wajah", uz: "Yuz yuvish vositasi", ru: "Средство для умывания" }, image: img("1620916566398-39f1143ab7be") },
  { id: "c-moist-cream", slug: "moist-cream", departmentId: "dept-skincare", names: { en: "Moist Cream", id: "Krim Pelembap", uz: "Namlovchi krem", ru: "Увлажняющий крем" }, image: img("1670201202833-b0932731628f") },
  { id: "c-sunscreen", slug: "sunscreen", departmentId: "dept-skincare", names: { en: "Sunscreen", id: "Tabir Surya", uz: "Quyoshdan himoya", ru: "Солнцезащитный крем" }, image: img("1616750819456-5cdee9b85d22") },
  { id: "c-serum", slug: "serum", departmentId: "dept-skincare", names: { en: "Serum", id: "Serum", uz: "Syvorotka", ru: "Сыворотка" }, image: img("1613803745799-ba6c10aace85") },
  { id: "c-face-mist", slug: "face-mist", departmentId: "dept-skincare", names: { en: "Face Mist", id: "Face Mist", uz: "Yuz spreyi", ru: "Мист для лица" }, image: img("1616750819456-5cdee9b85d22") },
];

export const DEMO_PRODUCTS = [
  { id: "p1", name: "Gray Sweat Oversized Full-Zip Hoodie", price: 499000, compareAt: null, image: img("1564557287817-3785e38ec1f5"), colors: ["#8A8A8A", "#1A1A1A", "#D9C7A7", "#22304A"], meta: "WOMEN, XS–XXL", badge: "new" },
  { id: "p2", name: "Cloud White Oversized Hoodie", price: 479000, compareAt: null, image: img("1663573688938-2b3e7ea2ab33"), colors: ["#F5F5F5", "#8A8A8A"], meta: "UNISEX, XS–XXL", badge: null },
  { id: "p3", name: "Premium Chiffon Hijab", price: 89000, compareAt: null, image: img("1759150370507-87e833629a1a"), colors: ["#1A1A1A", "#7A2E3A", "#D9C7A7", "#22304A", "#6B6B4E"], meta: "WOMEN, 180×70 CM", badge: null },
  { id: "p4", name: "Gamis A-Line Dress", price: 389000, compareAt: 459000, image: img("1761014219840-60329882ca51"), colors: ["#F5F5F5", "#D9C7A7"], meta: "WOMEN, S–XL", badge: "sale" },
  { id: "p5", name: "Abaya Classic Black", price: 549000, compareAt: null, image: img("1718230800381-1b7ee3bfb2bd"), colors: ["#1A1A1A"], meta: "WOMEN, S–XXL", badge: null },
  { id: "p6", name: "Tunik Linen Relaxed", price: 299000, compareAt: null, image: img("1728485292065-bccf7eab3287"), colors: ["#D9C7A7", "#6B6B4E", "#F5F5F5"], meta: "WOMEN, XS–XL", badge: "new" },
  { id: "p7", name: "Halal Gentle Facial Wash 100ml", price: 79000, compareAt: null, image: img("1620916566398-39f1143ab7be"), colors: [], meta: "SKINCARE, 100 ML", badge: null },
  { id: "p8", name: "Brightening Serum 30ml", price: 149000, compareAt: 189000, image: img("1613803745799-ba6c10aace85"), colors: [], meta: "SKINCARE, 30 ML", badge: "sale" },
  { id: "p9", name: "Tropical Moist Cream 50ml", price: 129000, compareAt: null, image: img("1670201202833-b0932731628f"), colors: [], meta: "SKINCARE, 50 ML", badge: null },
  { id: "p10", name: "Wool Blend Outer Parka", price: 899000, compareAt: null, image: img("1618244965061-1d27b208d6e8"), colors: ["#6B6B4E", "#1A1A1A"], meta: "UNISEX, XS–XL", badge: "new" },
];

export const localizedName = (obj, locale) =>
  obj.names[locale] ?? obj.names.en;
