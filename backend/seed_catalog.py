"""Idempotent catalog seed for MUSLIMAH CANTIK (Milestone 2).

Run: python3 seed_catalog.py
Creates departments, categories, sellers, products, variants, indexes.
"""

import asyncio

from database import db
from models import Category, Product, ProductVariant, User


def img(photo_id, w=800):
    return (
        f"https://images.unsplash.com/photo-{photo_id}"
        f"?crop=entropy&cs=srgb&fm=jpg&q=80&w={w}&fit=crop"
    )


DEPARTMENTS = [
    (
        "women-muslimah",
        1,
        {
            "en": "Women Muslimah",
            "id": "Busana Muslimah",
            "uz": "Muslima ayollar",
            "ru": "Женская мусульманская",
        },
    ),
    (
        "uniqlo-products",
        2,
        {
            "en": "UNIQLO Products",
            "id": "Produk UNIQLO",
            "uz": "UNIQLO mahsulotlari",
            "ru": "Товары UNIQLO",
        },
    ),
    (
        "tropical-halal-skincare",
        3,
        {
            "en": "Tropical Halal Skincare",
            "id": "Skincare Halal Tropis",
            "uz": "Tropik halol teri parvarishi",
            "ru": "Тропический халяль-уход",
        },
    ),
]

MUSLIMAH_CATEGORIES = [
    ("hijab-kerudung", 1, {"en": "Hijab / Kerudung", "id": "Hijab / Kerudung", "uz": "Hijob", "ru": "Хиджаб"}),
    ("gamis", 2, {"en": "Gamis", "id": "Gamis", "uz": "Gamis", "ru": "Гамис"}),
    ("abaya", 3, {"en": "Abaya", "id": "Abaya", "uz": "Abaya", "ru": "Абая"}),
    ("tunik", 4, {"en": "Tunic", "id": "Tunik", "uz": "Tunika", "ru": "Туника"}),
    ("blouse-muslimah", 5, {"en": "Muslimah Blouse", "id": "Blouse Muslimah", "uz": "Muslima bluzkasi", "ru": "Мусульманская блуза"}),
    ("dress-muslimah", 6, {"en": "Muslimah Dress", "id": "Dress Muslimah", "uz": "Muslima ko'ylagi", "ru": "Мусульманское платье"}),
    ("setelan-muslimah", 7, {"en": "Muslimah Set", "id": "Setelan Muslimah", "uz": "Muslima to'plami", "ru": "Мусульманский комплект"}),
    ("outer-muslimah", 8, {"en": "Muslimah Outerwear", "id": "Outer Muslimah", "uz": "Muslima ustki kiyimi", "ru": "Мусульманская верхняя одежда"}),
    ("rok-muslimah", 9, {"en": "Muslimah Skirt", "id": "Rok Muslimah", "uz": "Muslima yubkasi", "ru": "Мусульманская юбка"}),
    ("celana-muslimah", 10, {"en": "Muslimah Pants", "id": "Celana Muslimah", "uz": "Muslima shimlari", "ru": "Мусульманские брюки"}),
    ("mukena", 11, {"en": "Mukena (Prayer Wear)", "id": "Mukena", "uz": "Mukena", "ru": "Мукена"}),
    ("busana-syari", 12, {"en": "Syar'i Wear", "id": "Busana Syar'i", "uz": "Shariat kiyimlari", "ru": "Шариатская одежда"}),
    ("busana-muslimah-kerja", 13, {"en": "Muslimah Workwear", "id": "Busana Muslimah Kerja", "uz": "Muslima ish kiyimlari", "ru": "Мусульманская рабочая одежда"}),
    ("busana-muslimah-pesta", 14, {"en": "Muslimah Party Wear", "id": "Busana Muslimah Pesta", "uz": "Muslima bayram kiyimlari", "ru": "Мусульманская праздничная одежда"}),
    ("busana-muslimah-hamil-menyusui", 15, {"en": "Maternity & Nursing Wear", "id": "Busana Muslimah Hamil & Menyusui", "uz": "Homilador va emizish kiyimlari", "ru": "Одежда для беременных и кормящих"}),
    ("busana-muslimah-olahraga", 16, {"en": "Muslimah Sportswear", "id": "Busana Muslimah Olahraga", "uz": "Muslima sport kiyimlari", "ru": "Мусульманская спортивная одежда"}),
    ("busana-muslimah-anak", 17, {"en": "Kids' Muslimah Wear", "id": "Busana Muslimah Anak", "uz": "Bolalar muslima kiyimlari", "ru": "Детская мусульманская одежда"}),
]

UNIQLO_CATEGORIES = [
    ("outerwear", 1, {"en": "Outerwear", "id": "Outerwear", "uz": "Ustki kiyimlar", "ru": "Верхняя одежда"}),
    ("tshirts-sweats-fleece", 2, {"en": "T-Shirts, Sweats & Fleece", "id": "Kaos, Sweat & Fleece", "uz": "Futbolkalar, svitshotlar va flis", "ru": "Футболки, свитшоты и флис"}),
    ("sweatshirts-hoodies", 3, {"en": "Sweatshirts & Hoodies", "id": "Sweatshirt & Hoodie", "uz": "Svitshotlar va xudilar", "ru": "Свитшоты и худи"}),
    ("bottoms", 4, {"en": "Bottoms", "id": "Bawahan", "uz": "Shimlar", "ru": "Низ"}),
    ("shirts-blouses", 5, {"en": "Shirts & Blouses", "id": "Kemeja & Blus", "uz": "Ko'ylak va bluzkalar", "ru": "Рубашки и блузы"}),
    ("sweaters-knitwear", 6, {"en": "Sweaters & Knitwear", "id": "Sweater & Rajutan", "uz": "Sviterlar va trikotaj", "ru": "Свитеры и трикотаж"}),
    ("dresses-skirts", 7, {"en": "Dresses & Skirts", "id": "Dress & Rok", "uz": "Ko'ylaklar va yubkalar", "ru": "Платья и юбки"}),
    ("loungewear-home", 8, {"en": "Loungewear & Home", "id": "Loungewear & Rumah", "uz": "Uy kiyimlari", "ru": "Домашняя одежда"}),
]

SKINCARE_CATEGORIES = [
    ("facial-wash", 1, {"en": "Facial Wash", "id": "Sabun Wajah", "uz": "Yuz yuvish vositasi", "ru": "Средство для умывания"}),
    ("moist-cream", 2, {"en": "Moist Cream", "id": "Krim Pelembap", "uz": "Namlovchi krem", "ru": "Увлажняющий крем"}),
    ("sunscreen", 3, {"en": "Sunscreen", "id": "Tabir Surya", "uz": "Quyoshdan himoya", "ru": "Солнцезащитный крем"}),
    ("serum", 4, {"en": "Serum", "id": "Serum", "uz": "Syvorotka", "ru": "Сыворотка"}),
    ("face-mist", 5, {"en": "Face Mist", "id": "Face Mist", "uz": "Yuz spreyi", "ru": "Мист для лица"}),
]

SELLERS = [
    ("official@muslimahcantik.id", "MUSLIMAH CANTIK Official"),
    ("partner-uniqlo@muslimahcantik.id", "UNIQLO Products Partner"),
    ("tropicalglow@muslimahcantik.id", "Tropical Glow Halal Beauty"),
]

SIZES_6 = ["XS", "S", "M", "L", "XL", "XXL"]
SIZES_4 = ["S", "M", "L", "XL"]


def tr(en, id_, uz, ru):
    return {
        "en": {"title": en},
        "id": {"title": id_},
        "uz": {"title": uz},
        "ru": {"title": ru},
    }


def color_size_variants(prefix, colors, sizes, stock=12, overrides=None, zero=None, low=None):
    overrides = overrides or {}
    zero = zero or set()
    low = low or set()
    variants = []
    for c_name, c_code in colors:
        for size in sizes:
            sku = f"{prefix}-{c_code}-{size}"
            s = stock
            if (c_code, size) in zero:
                s = 0
            elif (c_code, size) in low:
                s = 2
            variants.append(
                {
                    "sku": sku,
                    "option_values": {"color": c_name, "size": size},
                    "stock_quantity": s,
                    "price_override": overrides.get(size),
                }
            )
    return variants


PRODUCTS = [
    {
        "slug": "gray-sweat-oversized-full-zip-hoodie",
        "category": "sweatshirts-hoodies",
        "seller": "partner-uniqlo@muslimahcantik.id",
        "product_type": "apparel",
        "brand": "MC Essentials",
        "base_price": 499000,
        "compare_at_price": None,
        "tags": ["hoodie", "full-zip", "oversized", "sweat"],
        "attributes": {"fit": "oversized", "fabric": "cotton fleece"},
        "media": [img("1564557287817-3785e38ec1f5")],
        "new_arrival": True,
        "bestseller": False,
        "featured": True,
        "translations": {
            "en": {"title": "Gray Sweat Oversized Full-Zip Hoodie", "description": "Oversized full-zip hoodie in soft cotton fleece."},
            "id": {"title": "Hoodie Full-Zip Oversized Sweat Abu", "description": "Hoodie full-zip oversized dari bahan fleece katun lembut."},
            "uz": {"title": "Kulrang oversized svitshot-xudi", "description": "Yumshoq paxta flisdan oversized xudi."},
            "ru": {"title": "Серая oversized-худи на молнии", "description": "Oversized-худи из мягкого хлопкового флиса."},
        },
        "variants": color_size_variants(
            "GSOZH",
            [("Gray", "GRY"), ("Black", "BLK"), ("Beige", "BGE"), ("Navy", "NVY")],
            SIZES_6,
            stock=12,
            overrides={"XXL": 519000},
            zero={("BLK", "XXL")},
            low={("GRY", "XS")},
        ),
    },
    {
        "slug": "essential-crewneck-sweatshirt",
        "category": "tshirts-sweats-fleece",
        "seller": "partner-uniqlo@muslimahcantik.id",
        "product_type": "apparel",
        "brand": "MC Essentials",
        "base_price": 349000,
        "compare_at_price": None,
        "tags": ["sweatshirt", "crewneck", "basic"],
        "attributes": {"fit": "regular", "fabric": "cotton fleece"},
        "media": [img("1504198458649-3128b932f49e")],
        "new_arrival": False,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": {"title": "Essential Crewneck Sweatshirt", "description": "Everyday crewneck sweatshirt with a clean silhouette."},
            "id": {"title": "Sweatshirt Crewneck Essential", "description": "Sweatshirt crewneck harian dengan siluet bersih."},
            "uz": {"title": "Essential svitshot", "description": "Kundalik foydalanish uchun oddiy svitshot."},
            "ru": {"title": "Базовый свитшот с круглым вырезом", "description": "Повседневный свитшот с чистым силуэтом."},
        },
        "variants": color_size_variants(
            "ECSW",
            [("Off White", "OWH"), ("Gray", "GRY"), ("Black", "BLK")],
            SIZES_4,
            stock=15,
        ),
    },
    {
        "slug": "wide-leg-relaxed-trousers",
        "category": "bottoms",
        "seller": "partner-uniqlo@muslimahcantik.id",
        "product_type": "apparel",
        "brand": "MC Essentials",
        "base_price": 399000,
        "compare_at_price": 459000,
        "tags": ["trousers", "wide-leg", "bottoms"],
        "attributes": {"fit": "wide-leg", "fabric": "rayon blend"},
        "media": [img("1699797467199-6bdf301649e8")],
        "new_arrival": False,
        "bestseller": True,
        "featured": False,
        "translations": {
            "en": {"title": "Wide-Leg Relaxed Trousers", "description": "Relaxed wide-leg trousers with a fluid drape."},
            "id": {"title": "Celana Wide-Leg Relaxed", "description": "Celana wide-leg santai dengan jatuh kain yang fluid."},
            "uz": {"title": "Keng kesimli erkin shim", "description": "Yumshoq tushadigan keng kesimli shim."},
            "ru": {"title": "Широкие брюки relaxed", "description": "Свободные широкие брюки с плавной драпировкой."},
        },
        "variants": color_size_variants(
            "WLRT",
            [("Black", "BLK"), ("Beige", "BGE")],
            SIZES_4,
            stock=10,
        ),
    },
    {
        "slug": "premium-chiffon-hijab",
        "category": "hijab-kerudung",
        "seller": "official@muslimahcantik.id",
        "product_type": "apparel",
        "brand": "MUSLIMAH CANTIK",
        "base_price": 89000,
        "compare_at_price": None,
        "tags": ["hijab", "chiffon", "voal"],
        "attributes": {"size_cm": "180x70"},
        "media": [img("1550546094-9835463f9f71")],
        "new_arrival": False,
        "bestseller": True,
        "featured": True,
        "translations": {
            "en": {"title": "Premium Chiffon Hijab", "description": "Lightweight premium hijab with an elegant drape."},
            "id": {"title": "Hijab Chiffon Premium", "description": "Hijab premium ringan dengan jatuh kain yang elegan."},
            "uz": {"title": "Premium shifon hijob", "description": "Nafis tushadigan yengil premium hijob."},
            "ru": {"title": "Премиальный шифоновый хиджаб", "description": "Лёгкий премиальный хиджаб с элегантной драпировкой."},
        },
        "variants": [
            {"sku": "PCH-BLK-VOL", "option_values": {"color": "Black", "material": "Voal"}, "stock_quantity": 20},
            {"sku": "PCH-NVY-VOL", "option_values": {"color": "Navy", "material": "Voal"}, "stock_quantity": 20},
            {"sku": "PCH-BGE-CHF", "option_values": {"color": "Beige", "material": "Chiffon"}, "stock_quantity": 5},
            {"sku": "PCH-MRN-CHF", "option_values": {"color": "Maroon", "material": "Chiffon"}, "stock_quantity": 0},
        ],
    },
    {
        "slug": "gamis-a-line-dress",
        "category": "gamis",
        "seller": "official@muslimahcantik.id",
        "product_type": "apparel",
        "brand": "MUSLIMAH CANTIK",
        "base_price": 389000,
        "compare_at_price": 459000,
        "tags": ["gamis", "dress", "a-line"],
        "attributes": {"fit": "a-line", "fabric": "soft crepe"},
        "media": [img("1779400882805-5d304490a5de")],
        "new_arrival": False,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": {"title": "Gamis A-Line Dress", "description": "Flowing A-line gamis dress in soft crepe."},
            "id": {"title": "Gamis A-Line", "description": "Gamis A-line mengalir dari bahan crepe lembut."},
            "uz": {"title": "A-kesim gamis", "description": "Yumshoq krepdan oqimli A-kesim gamis."},
            "ru": {"title": "Гамис А-силуэта", "description": "Струящийся гамис А-силуэта из мягкого крепа."},
        },
        "variants": color_size_variants(
            "GALD",
            [("Dusty Purple", "DPL"), ("Beige", "BGE")],
            ["S", "M", "L"],
            stock=9,
        ),
    },
    {
        "slug": "abaya-classic-black",
        "category": "abaya",
        "seller": "official@muslimahcantik.id",
        "product_type": "apparel",
        "brand": "MUSLIMAH CANTIK",
        "base_price": 549000,
        "compare_at_price": None,
        "tags": ["abaya", "black", "classic"],
        "attributes": {"fit": "straight", "fabric": "premium nida"},
        "media": [img("1762605135321-d025ebbd13d8")],
        "new_arrival": False,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": {"title": "Abaya Classic Black", "description": "Timeless black abaya in premium nida fabric."},
            "id": {"title": "Abaya Hitam Klasik", "description": "Abaya hitam klasik dari bahan nida premium."},
            "uz": {"title": "Klassik qora abaya", "description": "Premium nida matodan klassik qora abaya."},
            "ru": {"title": "Классическая чёрная абая", "description": "Вневременная чёрная абая из премиальной ткани нида."},
        },
        "variants": color_size_variants(
            "ACBK", [("Black", "BLK")], SIZES_4, stock=7
        ),
    },
    {
        "slug": "mukena-travel-set",
        "category": "mukena",
        "seller": "official@muslimahcantik.id",
        "product_type": "apparel",
        "brand": "MUSLIMAH CANTIK",
        "base_price": 259000,
        "compare_at_price": None,
        "tags": ["mukena", "prayer", "travel"],
        "attributes": {"includes": "pouch"},
        "media": [img("1728485292065-bccf7eab3287")],
        "new_arrival": True,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": {"title": "Mukena Travel Set", "description": "Compact travel mukena with matching pouch."},
            "id": {"title": "Mukena Travel Set", "description": "Mukena travel ringkas dengan pouch senada."},
            "uz": {"title": "Sayohat mukenasi to'plami", "description": "Sumkali ixcham sayohat mukenasi."},
            "ru": {"title": "Дорожный комплект мукены", "description": "Компактная дорожная мукена с чехлом."},
        },
        "variants": [
            {"sku": "MTS-WHT", "option_values": {"color": "White"}, "stock_quantity": 3},
            {"sku": "MTS-DPK", "option_values": {"color": "Dusty Pink"}, "stock_quantity": 8},
        ],
    },
    {
        "slug": "kids-muslimah-daily-set",
        "category": "busana-muslimah-anak",
        "seller": "official@muslimahcantik.id",
        "product_type": "apparel",
        "brand": "MUSLIMAH CANTIK Kids",
        "base_price": 229000,
        "compare_at_price": None,
        "tags": ["kids", "set", "muslimah"],
        "attributes": {"age_range": "4-10"},
        "media": [img("1763906802942-8b1959ad0698")],
        "new_arrival": True,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": {"title": "Kids Muslimah Daily Set", "description": "Comfortable daily muslimah set for kids."},
            "id": {"title": "Setelan Muslimah Anak Harian", "description": "Setelan muslimah anak yang nyaman untuk harian."},
            "uz": {"title": "Bolalar uchun kundalik muslima to'plami", "description": "Bolalar uchun qulay kundalik muslima to'plami."},
            "ru": {"title": "Детский мусульманский комплект", "description": "Удобный повседневный мусульманский комплект для детей."},
        },
        "variants": [
            {"sku": "KMDS-4", "option_values": {"size": "4"}, "stock_quantity": 11},
            {"sku": "KMDS-6", "option_values": {"size": "6"}, "stock_quantity": 11},
            {"sku": "KMDS-8", "option_values": {"size": "8"}, "stock_quantity": 11},
            {"sku": "KMDS-10", "option_values": {"size": "10"}, "stock_quantity": 11},
        ],
    },
    {
        "slug": "halal-gentle-facial-wash",
        "category": "facial-wash",
        "seller": "tropicalglow@muslimahcantik.id",
        "product_type": "skincare",
        "brand": "Tropical Glow",
        "base_price": 79000,
        "compare_at_price": None,
        "tags": ["facial wash", "halal", "gentle"],
        "attributes": {"halal_certified": True, "skin_type": "all"},
        "media": [img("1620916566398-39f1143ab7be")],
        "new_arrival": False,
        "bestseller": True,
        "featured": False,
        "translations": {
            "en": {"title": "Halal Gentle Facial Wash", "description": "Gentle halal-certified facial wash for daily use."},
            "id": {"title": "Sabun Wajah Halal Gentle", "description": "Sabun wajah lembut bersertifikat halal untuk pemakaian harian."},
            "uz": {"title": "Halol muloyim yuz yuvish vositasi", "description": "Kundalik foydalanish uchun halol sertifikatli muloyim vosita."},
            "ru": {"title": "Мягкое халяль-средство для умывания", "description": "Мягкое халяль-сертифицированное средство на каждый день."},
        },
        "variants": [
            {"sku": "HGFW-50ML", "option_values": {"volume": "50 ml"}, "stock_quantity": 25, "price_override": 49000},
            {"sku": "HGFW-100ML", "option_values": {"volume": "100 ml"}, "stock_quantity": 30},
        ],
    },
    {
        "slug": "brightening-serum-30ml",
        "category": "serum",
        "seller": "tropicalglow@muslimahcantik.id",
        "product_type": "skincare",
        "brand": "Tropical Glow",
        "base_price": 149000,
        "compare_at_price": 189000,
        "tags": ["serum", "brightening", "halal"],
        "attributes": {"halal_certified": True, "active": "niacinamide"},
        "media": [img("1613803745799-ba6c10aace85")],
        "new_arrival": False,
        "bestseller": True,
        "featured": True,
        "translations": {
            "en": {"title": "Brightening Serum 30ml", "description": "Halal brightening serum with niacinamide."},
            "id": {"title": "Serum Brightening 30ml", "description": "Serum pencerah halal dengan niacinamide."},
            "uz": {"title": "Yorituvchi syvorotka 30 ml", "description": "Niacinamidli halol yorituvchi syvorotka."},
            "ru": {"title": "Осветляющая сыворотка 30 мл", "description": "Халяль-сыворотка с ниацинамидом."},
        },
        "variants": [
            {"sku": "BRS-30ML", "option_values": {"volume": "30 ml"}, "stock_quantity": 14},
        ],
    },
    {
        "slug": "tropical-moist-cream-50ml",
        "category": "moist-cream",
        "seller": "tropicalglow@muslimahcantik.id",
        "product_type": "skincare",
        "brand": "Tropical Glow",
        "base_price": 129000,
        "compare_at_price": None,
        "tags": ["moisturizer", "cream", "halal"],
        "attributes": {"halal_certified": True, "skin_type": "dry"},
        "media": [img("1670201202833-b0932731628f")],
        "new_arrival": False,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": {"title": "Tropical Moist Cream 50ml", "description": "Rich halal moist cream for tropical climates."},
            "id": {"title": "Krim Pelembap Tropis 50ml", "description": "Krim pelembap halal yang rich untuk iklim tropis."},
            "uz": {"title": "Tropik namlovchi krem 50 ml", "description": "Tropik iqlim uchun boy halol namlovchi krem."},
            "ru": {"title": "Тропический увлажняющий крем 50 мл", "description": "Насыщенный халяль-крем для тропического климата."},
        },
        "variants": [
            {"sku": "TMC-50ML", "option_values": {"volume": "50 ml"}, "stock_quantity": 0},
        ],
    },
    {
        "slug": "halal-daily-sunscreen-spf50",
        "category": "sunscreen",
        "seller": "tropicalglow@muslimahcantik.id",
        "product_type": "skincare",
        "brand": "Tropical Glow",
        "base_price": 119000,
        "compare_at_price": None,
        "tags": ["sunscreen", "spf50", "halal"],
        "attributes": {"halal_certified": True, "spf": 50},
        "media": [img("1616750819456-5cdee9b85d22")],
        "new_arrival": True,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": {"title": "Halal Daily Sunscreen SPF50", "description": "Lightweight halal sunscreen for tropical sun."},
            "id": {"title": "Tabir Surya Harian Halal SPF50", "description": "Tabir surya halal ringan untuk matahari tropis."},
            "uz": {"title": "Halol kundalik quyoshdan himoya SPF50", "description": "Tropik quyosh uchun yengil halol krem."},
            "ru": {"title": "Халяль-солнцезащитный крем SPF50", "description": "Лёгкий халяль-крем для тропического солнца."},
        },
        "variants": [
            {"sku": "HDS-40ML", "option_values": {"volume": "40 ml"}, "stock_quantity": 18},
        ],
    },
]


async def upsert_one(collection, key, doc):
    payload = {k: v for k, v in doc.to_mongo().items() if k != "_id"}
    await collection.update_one({key: payload[key]}, {"$set": payload}, upsert=True)
    found = await collection.find_one({key: payload[key]}, {"_id": 1})
    return str(found["_id"])


async def seed():
    # Indexes (idempotent)
    await db.categories.create_index("slug", unique=True)
    await db.categories.create_index("parent_id")
    await db.products.create_index("slug", unique=True)
    await db.products.create_index("category_id")
    await db.products.create_index("seller_id")
    await db.products.create_index("status")
    await db.products.create_index("new_arrival")
    await db.product_variants.create_index("sku", unique=True)
    await db.product_variants.create_index("product_id")

    # Sellers
    seller_ids = {}
    for email, name in SELLERS:
        seller_ids[email] = await upsert_one(
            db.users, "email", User(email=email, full_name=name, role="seller")
        )

    # Departments
    dept_ids = {}
    for slug, order, names in DEPARTMENTS:
        dept_ids[slug] = await upsert_one(
            db.categories,
            "slug",
            Category(
                kind="department",
                department=slug,
                slug=slug,
                sort_order=order,
                translations={loc: {"title": n} for loc, n in names.items()},
            ),
        )

    # Categories
    cat_ids = {}
    groups = [
        ("women-muslimah", MUSLIMAH_CATEGORIES),
        ("uniqlo-products", UNIQLO_CATEGORIES),
        ("tropical-halal-skincare", SKINCARE_CATEGORIES),
    ]
    for dept_slug, cats in groups:
        for slug, order, names in cats:
            cat_ids[slug] = await upsert_one(
                db.categories,
                "slug",
                Category(
                    kind="category",
                    department=dept_slug,
                    slug=slug,
                    parent_id=dept_ids[dept_slug],
                    sort_order=order,
                    translations={loc: {"title": n} for loc, n in names.items()},
                ),
            )

    # Products + variants
    variant_total = 0
    for spec in PRODUCTS:
        product_id = await upsert_one(
            db.products,
            "slug",
            Product(
                seller_id=seller_ids[spec["seller"]],
                category_id=cat_ids[spec["category"]],
                product_type=spec["product_type"],
                slug=spec["slug"],
                translations=spec["translations"],
                brand=spec["brand"],
                base_price=spec["base_price"],
                compare_at_price=spec["compare_at_price"],
                currency="IDR",
                attributes=spec["attributes"],
                tags=spec["tags"],
                media=[{"url": u, "alt": spec["slug"], "sort_order": i} for i, u in enumerate(spec["media"])],
                status="active",
                featured=spec["featured"],
                bestseller=spec["bestseller"],
                new_arrival=spec["new_arrival"],
            ),
        )
        for v in spec["variants"]:
            await upsert_one(
                db.product_variants,
                "sku",
                ProductVariant(
                    product_id=product_id,
                    sku=v["sku"],
                    option_values=v["option_values"],
                    stock_quantity=v["stock_quantity"],
                    price_override=v.get("price_override"),
                ),
            )
            variant_total += 1

    counts = {
        "departments": await db.categories.count_documents({"kind": "department"}),
        "categories": await db.categories.count_documents({"kind": "category"}),
        "sellers": await db.users.count_documents({"role": "seller"}),
        "products": await db.products.count_documents({}),
        "variants": await db.product_variants.count_documents({}),
    }
    print("SEED COMPLETE:", counts)


if __name__ == "__main__":
    asyncio.run(seed())
