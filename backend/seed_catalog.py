"""Idempotent catalog seed for MUSLIMAH CANTIK (PostgreSQL, Milestone 3).

Run: python3 seed_catalog.py
Creates departments, categories (+translations), the single store owner,
products (+translations), and variants. Safe to re-run.
"""

import asyncio
import os

from sqlalchemy import func, select

from db.models import (
    Category,
    CategoryTranslation,
    Product,
    ProductTranslation,
    ProductVariant,
    User,
)
from db.session import SessionLocal


def img(*_args, **_kwargs):
    """Legacy seed signature; visual assets are imported through CMS."""
    return None


DEPARTMENTS = [
    ("women-muslimah", 1, {"en": "Women Muslimah", "id": "Busana Muslimah", "uz": "Muslima ayollar", "ru": "Женская мусульманская"}, img("1762376268273-645db555eaf9", 900), True),
    ("uniqlo-products", 2, {"en": "UNIQLO Products", "id": "Produk UNIQLO", "uz": "UNIQLO mahsulotlari", "ru": "Товары UNIQLO"}, img("1603400521630-9f2de124b33b", 900), True),
    ("tropical-halal-skincare", 3, {"en": "Tropical Halal Skincare", "id": "Skincare Halal Tropis", "uz": "Tropik halol teri parvarishi", "ru": "Тропический халяль-уход"}, img("1616750819456-5cdee9b85d22", 900), True),
    # New commercial taxonomy is staged inactive until official products and
    # approved CMS visuals are imported.
    ("batik", 4, {"en": "Batik", "id": "Batik", "uz": "Batik", "ru": "Батик"}, None, False),
    ("parfum", 5, {"en": "Perfume", "id": "Parfum", "uz": "Atirlar", "ru": "Парфюмерия"}, None, False),
]

BATIK_WOMEN_CATEGORIES = [
    ("gamis-batik", 1, {"en": "Batik Gamis", "id": "Gamis Batik", "uz": "Batikli gamis", "ru": "Гамис из батика"}),
    ("tunik-batik", 2, {"en": "Batik Tunic", "id": "Tunik Batik", "uz": "Batik tunika", "ru": "Туника из батика"}),
    ("outer-cardigan-batik", 3, {"en": "Batik Outerwear & Cardigans", "id": "Outer & Cardigan Batik", "uz": "Batik ustki kiyimlari va kardiganlar", "ru": "Верхняя одежда и кардиганы из батика"}),
    ("setelan-one-set-batik", 4, {"en": "Batik One-Set", "id": "Setelan (One-Set Batik)", "uz": "Batikli komplekt", "ru": "Комплект из батика"}),
    ("rok-batik-panjang", 5, {"en": "Long Batik Skirts", "id": "Rok Batik Panjang", "uz": "Uzun batik yubkalar", "ru": "Длинные юбки из батика"}),
    ("hijab-pashmina-batik", 6, {"en": "Batik Hijab & Pashmina", "id": "Hijab & Pashmina Batik", "uz": "Batik hijob va pashmina", "ru": "Хиджабы и пашмины из батика"}),
]

BATIK_MEN_CATEGORIES = [
    ("batik-koko-kemko", 1, {"en": "Batik Koko (Kemko)", "id": "Batik Koko (Kemko)", "uz": "Batik koko (kemko)", "ru": "Батик-коко (кемко)"}),
    ("kemeja-batik-lengan-panjang", 2, {"en": "Long-Sleeve Batik Shirts", "id": "Kemeja Batik Lengan Panjang", "uz": "Uzun yengli batik ko'ylaklar", "ru": "Батиковые рубашки с длинным рукавом"}),
    ("kemeja-batik-lengan-pendek", 3, {"en": "Short-Sleeve Batik Shirts", "id": "Kemeja Batik Lengan Pendek", "uz": "Qisqa yengli batik ko'ylaklar", "ru": "Батиковые рубашки с коротким рукавом"}),
    ("jas-blazer-batik-luara", 4, {"en": "Batik Suits & Blazers: Luara", "id": "Jas & Blazer Batik: Luara", "uz": "Batik kostyum va blazerlar: Luara", "ru": "Костюмы и блейзеры из батика: Luara"}),
    ("sarung-batik", 5, {"en": "Batik Sarongs", "id": "Sarung Batik", "uz": "Batik sarunglar", "ru": "Батиковые саронги"}),
]

PARFUM_WOMEN_CATEGORIES = [
    ("musk-thaharah", 1, {"en": "Musk Thaharah", "id": "Musk Thaharah", "uz": "Musk Thaharah", "ru": "Муск Тахара"}),
    ("soft-floral-powdery", 2, {"en": "Soft Floral & Powdery (Light Daily Aroma)", "id": "Soft Floral & Powdery (Aroma Ringan Harian)", "uz": "Yumshoq floral va pudrali (yengil kundalik hid)", "ru": "Мягкий цветочный и пудровый аромат (лёгкий на каждый день)"}),
    ("gourmand-rich-oriental", 3, {"en": "Gourmand & Rich Oriental (Private/Home Use)", "id": "Gourmand & Rich Oriental (Khusus Area Privat/Rumah)", "uz": "Gurman va boy sharqona (uy va shaxsiy foydalanish)", "ru": "Гурманские и насыщенные восточные ароматы (для дома и личного использования)"}),
    ("parfum-semprot-bebas-alkohol", 4, {"en": "Alcohol-Free Spray Perfume", "id": "Parfum Semprot Bebas Alkohol (Alcohol-Free Spray)", "uz": "Spirtsiz purkaladigan atir", "ru": "Спрей-парфюм без спирта"}),
]

PARFUM_MEN_CATEGORIES = [
    ("oud-woody", 1, {"en": "Oud & Woody (Agarwood & Woods)", "id": "Oud & Woody (Gaharu & Kayu)", "uz": "Ud va yog'ochsimon (agar va yog'och)", "ru": "Удовые и древесные (агар и древесина)"}),
    ("kasturi-rempah", 2, {"en": "Musk & Spices", "id": "Kasturi & Rempah (Musk & Spices)", "uz": "Musk va ziravorlar", "ru": "Мускус и специи"}),
    ("fresh-citrus-aquatic", 3, {"en": "Fresh Citrus & Aquatic", "id": "Fresh Citrus & Aquatic", "uz": "Yangi sitrus va akvatik", "ru": "Свежие цитрусовые и акватические"}),
    ("attar-perfume-oil-premium", 4, {"en": "Premium Attar / Perfume Oil", "id": "Attar / Perfume Oil Premium", "uz": "Premium attor / atir moyi", "ru": "Премиальный аттар / парфюмерное масло"}),
]

NEW_TAXONOMY_GROUPS = [
    ("batik", "batik-wanita-muslimah", 1, {"en": "Batik Women Muslimah", "id": "Batik Wanita Muslimah", "uz": "Muslima ayollar batigi", "ru": "Батик для мусульманок"}, BATIK_WOMEN_CATEGORIES),
    ("batik", "batik-pria", 2, {"en": "Men's Batik", "id": "Batik Pria", "uz": "Erkaklar batigi", "ru": "Мужской батик"}, BATIK_MEN_CATEGORIES),
    ("parfum", "parfum-wanita-muslimah", 1, {"en": "Women Muslimah Perfume", "id": "Parfum Wanita Muslimah", "uz": "Muslima ayollar atirlari", "ru": "Парфюмерия для мусульманок"}, PARFUM_WOMEN_CATEGORIES),
    ("parfum", "parfum-pria", 2, {"en": "Men's Perfume", "id": "Parfum Pria", "uz": "Erkaklar atirlari", "ru": "Мужская парфюмерия"}, PARFUM_MEN_CATEGORIES),
]

MUSLIMAH_CATEGORIES = [
    ("hijab-kerudung", 1, {"en": "Hijab / Kerudung", "id": "Hijab / Kerudung", "uz": "Hijob", "ru": "Хиджаб"}, img("1550546094-9835463f9f71")),
    ("gamis", 2, {"en": "Gamis", "id": "Gamis", "uz": "Gamis", "ru": "Гамис"}, img("1779400882805-5d304490a5de")),
    ("abaya", 3, {"en": "Abaya", "id": "Abaya", "uz": "Abaya", "ru": "Абая"}, img("1762605135321-d025ebbd13d8")),
    ("tunik", 4, {"en": "Tunic", "id": "Tunik", "uz": "Tunika", "ru": "Туника"}, img("1728485292065-bccf7eab3287")),
    ("blouse-muslimah", 5, {"en": "Muslimah Blouse", "id": "Blouse Muslimah", "uz": "Muslima bluzkasi", "ru": "Мусульманская блуза"}, img("1574297500578-afae55026ff3")),
    ("dress-muslimah", 6, {"en": "Muslimah Dress", "id": "Dress Muslimah", "uz": "Muslima ko'ylagi", "ru": "Мусульманское платье"}, img("1761014219840-60329882ca51")),
    ("setelan-muslimah", 7, {"en": "Muslimah Set", "id": "Setelan Muslimah", "uz": "Muslima to'plami", "ru": "Мусульманский комплект"}, img("1552874869-5c39ec9288dc")),
    ("outer-muslimah", 8, {"en": "Muslimah Outerwear", "id": "Outer Muslimah", "uz": "Muslima ustki kiyimi", "ru": "Мусульманская верхняя одежда"}, img("1618244965061-1d27b208d6e8")),
    ("rok-muslimah", 9, {"en": "Muslimah Skirt", "id": "Rok Muslimah", "uz": "Muslima yubkasi", "ru": "Мусульманская юбка"}, img("1552874869-5c39ec9288dc")),
    ("celana-muslimah", 10, {"en": "Muslimah Pants", "id": "Celana Muslimah", "uz": "Muslima shimlari", "ru": "Мусульманские брюки"}, img("1699797467199-6bdf301649e8")),
    ("mukena", 11, {"en": "Mukena (Prayer Wear)", "id": "Mukena", "uz": "Mukena", "ru": "Мукена"}, img("1728485292065-bccf7eab3287")),
    ("busana-syari", 12, {"en": "Syar'i Wear", "id": "Busana Syar'i", "uz": "Shariat kiyimlari", "ru": "Шариатская одежда"}, img("1762376268273-645db555eaf9")),
    ("busana-muslimah-kerja", 13, {"en": "Muslimah Workwear", "id": "Busana Muslimah Kerja", "uz": "Muslima ish kiyimlari", "ru": "Мусульманская рабочая одежда"}, img("1574297500578-afae55026ff3")),
    ("busana-muslimah-pesta", 14, {"en": "Muslimah Party Wear", "id": "Busana Muslimah Pesta", "uz": "Muslima bayram kiyimlari", "ru": "Мусульманская праздничная одежда"}, img("1763906802942-8b1959ad0698")),
    ("busana-muslimah-hamil-menyusui", 15, {"en": "Maternity & Nursing Wear", "id": "Busana Muslimah Hamil & Menyusui", "uz": "Homilador va emizish kiyimlari", "ru": "Одежда для беременных и кормящих"}, img("1779400882805-5d304490a5de")),
    ("busana-muslimah-olahraga", 16, {"en": "Muslimah Sportswear", "id": "Busana Muslimah Olahraga", "uz": "Muslima sport kiyimlari", "ru": "Мусульманская спортивная одежда"}, img("1728485292065-bccf7eab3287")),
    ("busana-muslimah-anak", 17, {"en": "Kids' Muslimah Wear", "id": "Busana Muslimah Anak", "uz": "Bolalar muslima kiyimlari", "ru": "Детская мусульманская одежда"}, img("1763906802942-8b1959ad0698")),
]

UNIQLO_CATEGORIES = [
    ("outerwear", 1, {"en": "Outerwear", "id": "Outerwear", "uz": "Ustki kiyimlar", "ru": "Верхняя одежда"}, img("1618244965061-1d27b208d6e8")),
    ("tshirts-sweats-fleece", 2, {"en": "T-Shirts, Sweats & Fleece", "id": "Kaos, Sweat & Fleece", "uz": "Futbolkalar, svitshotlar va flis", "ru": "Футболки, свитшоты и флис"}, img("1619032468883-89a84f565cba")),
    ("sweatshirts-hoodies", 3, {"en": "Sweatshirts & Hoodies", "id": "Sweatshirt & Hoodie", "uz": "Svitshotlar va xudilar", "ru": "Свитшоты и худи"}, img("1504198458649-3128b932f49e")),
    ("bottoms", 4, {"en": "Bottoms", "id": "Bawahan", "uz": "Shimlar", "ru": "Низ"}, img("1699797467199-6bdf301649e8")),
    ("shirts-blouses", 5, {"en": "Shirts & Blouses", "id": "Kemeja & Blus", "uz": "Ko'ylak va bluzkalar", "ru": "Рубашки и блузы"}, img("1604506847073-4a8e18e07d92")),
    ("sweaters-knitwear", 6, {"en": "Sweaters & Knitwear", "id": "Sweater & Rajutan", "uz": "Sviterlar va trikotaj", "ru": "Свитеры и трикотаж"}, img("1641642231157-0849081598a2")),
    ("dresses-skirts", 7, {"en": "Dresses & Skirts", "id": "Dress & Rok", "uz": "Ko'ylaklar va yubkalar", "ru": "Платья и юбки"}, img("1645088930126-f669feb0fc5f")),
    ("loungewear-home", 8, {"en": "Loungewear & Home", "id": "Loungewear & Rumah", "uz": "Uy kiyimlari", "ru": "Домашняя одежда"}, img("1603400521630-9f2de124b33b")),
]

SKINCARE_CATEGORIES = [
    ("facial-wash", 1, {"en": "Facial Wash", "id": "Sabun Wajah", "uz": "Yuz yuvish vositasi", "ru": "Средство для умывания"}, img("1620916566398-39f1143ab7be")),
    ("moist-cream", 2, {"en": "Moist Cream", "id": "Krim Pelembap", "uz": "Namlovchi krem", "ru": "Увлажняющий крем"}, img("1670201202833-b0932731628f")),
    ("sunscreen", 3, {"en": "Sunscreen", "id": "Tabir Surya", "uz": "Quyoshdan himoya", "ru": "Солнцезащитный крем"}, img("1616750819456-5cdee9b85d22")),
    ("serum", 4, {"en": "Serum", "id": "Serum", "uz": "Syvorotka", "ru": "Сыворотка"}, img("1613803745799-ba6c10aace85")),
    ("face-mist", 5, {"en": "Face Mist", "id": "Face Mist", "uz": "Yuz spreyi", "ru": "Мист для лица"}, img("1616750819456-5cdee9b85d22")),
]

STORE_OWNER = ("official@muslimahcantik.id", "MUSLIMAH CANTIK Official")

SIZES_6 = ["XS", "S", "M", "L", "XL", "XXL"]
SIZES_4 = ["S", "M", "L", "XL"]


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
        "product_type": "apparel",
        "brand": "MC Essentials",
        "base_price": 499000,
        "compare_at_price": None,
        "tags": ["hoodie", "full-zip", "oversized", "sweat"],
        "attributes": {"fit": "oversized", "fabric": "100% cotton fleece", "care": "Machine wash cold, tumble dry low"},
        "media": [img("1564557287817-3785e38ec1f5"), img("1542406775-ade58c52d2e4")],
        "new_arrival": True,
        "bestseller": False,
        "featured": True,
        "translations": {
            "en": ("Gray Sweat Oversized Full-Zip Hoodie", "Oversized full-zip hoodie in soft cotton fleece."),
            "id": ("Hoodie Full-Zip Oversized Sweat Abu", "Hoodie full-zip oversized dari bahan fleece katun lembut."),
            "uz": ("Kulrang oversized svitshot-xudi", "Yumshoq paxta flisdan oversized xudi."),
            "ru": ("Серая oversized-худи на молнии", "Oversized-худи из мягкого хлопкового флиса."),
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
            "en": ("Essential Crewneck Sweatshirt", "Everyday crewneck sweatshirt with a clean silhouette."),
            "id": ("Sweatshirt Crewneck Essential", "Sweatshirt crewneck harian dengan siluet bersih."),
            "uz": ("Essential svitshot", "Kundalik foydalanish uchun oddiy svitshot."),
            "ru": ("Базовый свитшот с круглым вырезом", "Повседневный свитшот с чистым силуэтом."),
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
            "en": ("Wide-Leg Relaxed Trousers", "Relaxed wide-leg trousers with a fluid drape."),
            "id": ("Celana Wide-Leg Relaxed", "Celana wide-leg santai dengan jatuh kain yang fluid."),
            "uz": ("Keng kesimli erkin shim", "Yumshoq tushadigan keng kesimli shim."),
            "ru": ("Широкие брюки relaxed", "Свободные широкие брюки с плавной драпировкой."),
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
        "product_type": "apparel",
        "brand": "MUSLIMAH CANTIK",
        "base_price": 89000,
        "compare_at_price": None,
        "tags": ["hijab", "chiffon", "voal"],
        "attributes": {"size_cm": "180x70", "material": "Premium chiffon / voal", "care": "Hand wash cold, hang dry"},
        "media": [img("1550546094-9835463f9f71"), img("1759150370507-87e833629a1a")],
        "new_arrival": False,
        "bestseller": True,
        "featured": True,
        "translations": {
            "en": ("Premium Chiffon Hijab", "Lightweight premium hijab with an elegant drape."),
            "id": ("Hijab Chiffon Premium", "Hijab premium ringan dengan jatuh kain yang elegan."),
            "uz": ("Premium shifon hijob", "Nafis tushadigan yengil premium hijob."),
            "ru": ("Премиальный шифоновый хиджаб", "Лёгкий премиальный хиджаб с элегантной драпировкой."),
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
        "product_type": "apparel",
        "brand": "MUSLIMAH CANTIK",
        "base_price": 389000,
        "compare_at_price": 459000,
        "tags": ["gamis", "dress", "a-line"],
        "attributes": {"fit": "a-line", "fabric": "soft crepe", "care": "Machine wash cold, gentle cycle"},
        "media": [img("1779400882805-5d304490a5de")],
        "new_arrival": False,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": ("Gamis A-Line Dress", "Flowing A-line gamis dress in soft crepe."),
            "id": ("Gamis A-Line", "Gamis A-line mengalir dari bahan crepe lembut."),
            "uz": ("A-kesim gamis", "Yumshoq krepdan oqimli A-kesim gamis."),
            "ru": ("Гамис А-силуэта", "Струящийся гамис А-силуэта из мягкого крепа."),
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
        "product_type": "apparel",
        "brand": "MUSLIMAH CANTIK",
        "base_price": 549000,
        "compare_at_price": None,
        "tags": ["abaya", "black", "classic"],
        "attributes": {"fit": "straight", "fabric": "premium nida", "care": "Machine wash cold, hang dry"},
        "media": [img("1762605135321-d025ebbd13d8")],
        "new_arrival": False,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": ("Abaya Classic Black", "Timeless black abaya in premium nida fabric."),
            "id": ("Abaya Hitam Klasik", "Abaya hitam klasik dari bahan nida premium."),
            "uz": ("Klassik qora abaya", "Premium nida matodan klassik qora abaya."),
            "ru": ("Классическая чёрная абая", "Вневременная чёрная абая из премиальной ткани нида."),
        },
        "variants": color_size_variants(
            "ACBK", [("Black", "BLK")], SIZES_4, stock=7
        ),
    },
    {
        "slug": "mukena-travel-set",
        "category": "mukena",
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
            "en": ("Mukena Travel Set", "Compact travel mukena with matching pouch."),
            "id": ("Mukena Travel Set", "Mukena travel ringkas dengan pouch senada."),
            "uz": ("Sayohat mukenasi to'plami", "Sumkali ixcham sayohat mukenasi."),
            "ru": ("Дорожный комплект мукены", "Компактная дорожная мукена с чехлом."),
        },
        "variants": [
            {"sku": "MTS-WHT", "option_values": {"color": "White"}, "stock_quantity": 3},
            {"sku": "MTS-DPK", "option_values": {"color": "Dusty Pink"}, "stock_quantity": 8},
        ],
    },
    {
        "slug": "kids-muslimah-daily-set",
        "category": "busana-muslimah-anak",
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
            "en": ("Kids Muslimah Daily Set", "Comfortable daily muslimah set for kids."),
            "id": ("Setelan Muslimah Anak Harian", "Setelan muslimah anak yang nyaman untuk harian."),
            "uz": ("Bolalar uchun kundalik muslima to'plami", "Bolalar uchun qulay kundalik muslima to'plami."),
            "ru": ("Детский мусульманский комплект", "Удобный повседневный мусульманский комплект для детей."),
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
        "product_type": "skincare",
        "brand": "Tropical Glow",
        "base_price": 79000,
        "compare_at_price": None,
        "tags": ["facial wash", "halal", "gentle"],
        "attributes": {"halal_certified": True, "skin_type": "all", "ingredients": "Aqua, glycerin, coco-glucoside, panthenol", "benefits": "Gentle cleansing without stripping", "directions": "Massage onto damp face, then rinse"},
        "media": [img("1620916566398-39f1143ab7be")],
        "new_arrival": False,
        "bestseller": True,
        "featured": False,
        "translations": {
            "en": ("Halal Gentle Facial Wash", "Gentle halal-certified facial wash for daily use."),
            "id": ("Sabun Wajah Halal Gentle", "Sabun wajah lembut bersertifikat halal untuk pemakaian harian."),
            "uz": ("Halol muloyim yuz yuvish vositasi", "Kundalik foydalanish uchun halol sertifikatli muloyim vosita."),
            "ru": ("Мягкое халяль-средство для умывания", "Мягкое халяль-сертифицированное средство на каждый день."),
        },
        "variants": [
            {"sku": "HGFW-50ML", "option_values": {"volume": "50 ml"}, "stock_quantity": 25, "price_override": 49000},
            {"sku": "HGFW-100ML", "option_values": {"volume": "100 ml"}, "stock_quantity": 30},
        ],
    },
    {
        "slug": "brightening-serum-30ml",
        "category": "serum",
        "product_type": "skincare",
        "brand": "Tropical Glow",
        "base_price": 149000,
        "compare_at_price": 189000,
        "tags": ["serum", "brightening", "halal"],
        "attributes": {"halal_certified": True, "active": "niacinamide", "ingredients": "Niacinamide 5%, hyaluronic acid, vitamin E", "benefits": "Brightens and evens skin tone", "directions": "Apply 2-3 drops morning and night"},
        "media": [img("1613803745799-ba6c10aace85"), img("1620916566398-39f1143ab7be")],
        "new_arrival": False,
        "bestseller": True,
        "featured": True,
        "translations": {
            "en": ("Brightening Serum 30ml", "Halal brightening serum with niacinamide."),
            "id": ("Serum Brightening 30ml", "Serum pencerah halal dengan niacinamide."),
            "uz": ("Yorituvchi syvorotka 30 ml", "Niacinamidli halol yorituvchi syvorotka."),
            "ru": ("Осветляющая сыворотка 30 мл", "Халяль-сыворотка с ниацинамидом."),
        },
        "variants": [
            {"sku": "BRS-30ML", "option_values": {"volume": "30 ml"}, "stock_quantity": 14},
        ],
    },
    {
        "slug": "tropical-moist-cream-50ml",
        "category": "moist-cream",
        "product_type": "skincare",
        "brand": "Tropical Glow",
        "base_price": 129000,
        "compare_at_price": None,
        "tags": ["moisturizer", "cream", "halal"],
        "attributes": {"halal_certified": True, "skin_type": "dry", "benefits": "48-hour hydration", "directions": "Apply to face and neck after serum"},
        "media": [img("1670201202833-b0932731628f")],
        "new_arrival": False,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": ("Tropical Moist Cream 50ml", "Rich halal moist cream for tropical climates."),
            "id": ("Krim Pelembap Tropis 50ml", "Krim pelembap halal yang rich untuk iklim tropis."),
            "uz": ("Tropik namlovchi krem 50 ml", "Tropik iqlim uchun boy halol namlovchi krem."),
            "ru": ("Тропический увлажняющий крем 50 мл", "Насыщенный халяль-крем для тропического климата."),
        },
        "variants": [
            {"sku": "TMC-50ML", "option_values": {"volume": "50 ml"}, "stock_quantity": 0},
        ],
    },
    {
        "slug": "halal-daily-sunscreen-spf50",
        "category": "sunscreen",
        "product_type": "skincare",
        "brand": "Tropical Glow",
        "base_price": 119000,
        "compare_at_price": None,
        "tags": ["sunscreen", "spf50", "halal"],
        "attributes": {"halal_certified": True, "spf": 50, "benefits": "SPF50 PA++++ broad spectrum", "directions": "Apply 15 minutes before sun exposure"},
        "media": [img("1616750819456-5cdee9b85d22")],
        "new_arrival": True,
        "bestseller": False,
        "featured": False,
        "translations": {
            "en": ("Halal Daily Sunscreen SPF50", "Lightweight halal sunscreen for tropical sun."),
            "id": ("Tabir Surya Harian Halal SPF50", "Tabir surya halal ringan untuk matahari tropis."),
            "uz": ("Halol kundalik quyoshdan himoya SPF50", "Tropik quyosh uchun yengil halol krem."),
            "ru": ("Халяль-солнцезащитный крем SPF50", "Лёгкий халяль-крем для тропического солнца."),
        },
        "variants": [
            {"sku": "HDS-40ML", "option_values": {"volume": "40 ml"}, "stock_quantity": 18},
        ],
    },
]


async def upsert_category(
    session,
    *,
    slug,
    kind,
    department,
    names,
    sort_order,
    parent_id=None,
    image_url=None,
    is_active=True,
):
    existing = await session.scalar(select(Category).where(Category.slug == slug))
    if existing:
        existing.kind = kind
        existing.department = department
        existing.sort_order = sort_order
        existing.parent_id = parent_id
        # Never replace a CMS-managed image on a repeat seed.
        if image_url is not None and not existing.media_id:
            existing.image_url = image_url
        if existing.image_url and not existing.media_id and str(existing.image_url).startswith(("http://", "https://")):
            existing.image_url = None
        # Existing manual activation is authoritative for staged taxonomy.
        # Legacy catalog entries are still explicitly kept active by the seed.
        if is_active:
            existing.is_active = True
        cat = existing
        await session.execute(
            CategoryTranslation.__table__.delete().where(
                CategoryTranslation.category_id == cat.id
            )
        )
    else:
        cat = Category(
            slug=slug,
            kind=kind,
            department=department,
            sort_order=sort_order,
            parent_id=parent_id,
            image_url=None,
            is_active=is_active,
        )
        session.add(cat)
        await session.flush()
    for locale, name in names.items():
        session.add(CategoryTranslation(category_id=cat.id, locale=locale, name=name))
    await session.flush()
    return cat.id


async def upsert_product(session, spec, owner_id, cat_ids):
    existing = await session.scalar(select(Product).where(Product.slug == spec["slug"]))
    fields = dict(
        seller_id=owner_id,
        category_id=cat_ids[spec["category"]],
        product_type=spec["product_type"],
        brand=spec["brand"],
        base_price=spec["base_price"],
        compare_at_price=spec["compare_at_price"],
        currency="UZS",
        attributes=spec["attributes"],
        tags=spec["tags"],
        status="active",
        featured=spec["featured"],
        bestseller=spec["bestseller"],
        new_arrival=spec["new_arrival"],
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        # External demo images are not allowed to survive a seed rerun.
        existing.media = [
            item for item in (existing.media or [])
            if not (
                (
                    isinstance(item, str)
                    and item.startswith(("http://", "https://"))
                )
                or (
                    isinstance(item, dict)
                    and isinstance(item.get("url"), str)
                    and item["url"].startswith(("http://", "https://"))
                    and not item.get("media_id")
                )
            )
        ]
        product = existing
        await session.execute(
            ProductTranslation.__table__.delete().where(
                ProductTranslation.product_id == product.id
            )
        )
    else:
        product = Product(slug=spec["slug"], media=[], **fields)
        session.add(product)
        await session.flush()
    for locale, (name, desc) in spec["translations"].items():
        session.add(
            ProductTranslation(
                product_id=product.id, locale=locale, name=name, description=desc
            )
        )
    await session.flush()

    for v in spec["variants"]:
        existing_variant = await session.scalar(
            select(ProductVariant).where(ProductVariant.sku == v["sku"])
        )
        if existing_variant:
            existing_variant.product_id = product.id
            existing_variant.option_values = v["option_values"]
            existing_variant.stock_quantity = v["stock_quantity"]
            existing_variant.price_override = v.get("price_override")
            existing_variant.is_active = True
            if existing_variant.image_url and not existing_variant.media_id and str(existing_variant.image_url).startswith(("http://", "https://")):
                existing_variant.image_url = None
        else:
            session.add(
                ProductVariant(
                    product_id=product.id,
                    sku=v["sku"],
                    option_values=v["option_values"],
                    stock_quantity=v["stock_quantity"],
                    price_override=v.get("price_override"),
                )
            )
    await session.flush()


async def seed():
    async with SessionLocal() as session:
        email = (
            os.environ.get("STORE_OWNER_EMAIL", "").strip().lower()
            or os.environ.get("SEED_ADMIN_EMAIL", "").strip().lower()
            or STORE_OWNER[0]
        )
        name = STORE_OWNER[1]
        owner = await session.scalar(select(User).where(User.email == email))
        if not owner:
            owner = await session.scalar(
                select(User)
                .where(User.role.in_(("admin", "owner")), User.is_active.is_(True))
                .order_by(User.created_at, User.id)
            )
        if not owner:
            raise RuntimeError(
                "No active operator account found; run seed_accounts.py first"
            )
        owner.full_name = owner.full_name or name
        owner.role = "admin"
        owner.is_active = True

        dept_ids = {}
        for slug, order, names, image_url, is_active in DEPARTMENTS:
            dept_ids[slug] = await upsert_category(
                session,
                slug=slug,
                kind="department",
                department=slug,
                names=names,
                sort_order=order,
                image_url=image_url,
                is_active=is_active,
            )

        cat_ids = {}
        groups = [
            ("women-muslimah", MUSLIMAH_CATEGORIES),
            ("uniqlo-products", UNIQLO_CATEGORIES),
            ("tropical-halal-skincare", SKINCARE_CATEGORIES),
        ]
        for dept_slug, cats in groups:
            for slug, order, names, image_url in cats:
                cat_ids[slug] = await upsert_category(
                    session,
                    slug=slug,
                    kind="category",
                    department=dept_slug,
                    names=names,
                    sort_order=order,
                    parent_id=dept_ids[dept_slug],
                    image_url=image_url,
                )

        for root_slug, group_slug, group_order, group_names, leaf_specs in NEW_TAXONOMY_GROUPS:
            group_id = await upsert_category(
                session,
                slug=group_slug,
                kind="group",
                department=root_slug,
                names=group_names,
                sort_order=group_order,
                parent_id=dept_ids[root_slug],
                is_active=False,
            )
            for leaf_slug, leaf_order, leaf_names in leaf_specs:
                await upsert_category(
                    session,
                    slug=leaf_slug,
                    kind="category",
                    department=root_slug,
                    names=leaf_names,
                    sort_order=leaf_order,
                    parent_id=group_id,
                    is_active=False,
                )

        for spec in PRODUCTS:
            await upsert_product(session, spec, owner.id, cat_ids)

        await session.commit()

        counts = {
            "departments": await session.scalar(
                select(func.count()).select_from(Category).where(Category.kind == "department")
            ),
            "categories": await session.scalar(
                select(func.count()).select_from(Category).where(Category.kind == "category")
            ),
            "groups": await session.scalar(
                select(func.count()).select_from(Category).where(Category.kind == "group")
            ),
            "store_owners": await session.scalar(
                select(func.count()).select_from(User).where(User.id == owner.id)
            ),
            "products": await session.scalar(select(func.count()).select_from(Product)),
            "variants": await session.scalar(select(func.count()).select_from(ProductVariant)),
            "product_translations": await session.scalar(
                select(func.count()).select_from(ProductTranslation)
            ),
            "category_translations": await session.scalar(
                select(func.count()).select_from(CategoryTranslation)
            ),
        }
        print("SEED COMPLETE:", counts)


if __name__ == "__main__":
    asyncio.run(seed())
