"""Idempotent seed: migrate the approved hardcoded storefront content into
the CMS (draft->published), so the storefront can switch to CMS authority
without any visual change.

Reads the 4-locale strings straight from the frontend translations file to
avoid duplicating content. Existing operator-managed entries are preserved;
missing CMS homepage department visuals are added when their media is linked.
"""

import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select

from db.models import (
    Category,
    CategoryTranslation,
    CmsContentEntry,
    CmsContentTranslation,
    CmsMediaAsset,
    CmsMediaTranslation,
    Product,
)
from db.session import SessionLocal

TRANSLATIONS_PATH = os.environ.get(
    "FRONTEND_TRANSLATIONS_PATH",
    str(Path(__file__).resolve().parent.parent / "frontend" / "src" / "i18n" / "translations.js"),
)
LOCALES = ("en", "id", "uz", "ru")

EDITORIAL_SLUGS = (
    "modest-styling-guide",
    "hijab-styling-guide",
    "tropical-halal-skincare-routine",
    "new-season-muslimah-edit",
)

EDITORIAL_LABELS = {
    "modest-styling-guide": {"en": "Guide", "id": "Panduan", "uz": "Qo'llanma", "ru": "Гид"},
    "hijab-styling-guide": {"en": "Guide", "id": "Panduan", "uz": "Qo'llanma", "ru": "Гид"},
    "tropical-halal-skincare-routine": {"en": "Routine", "id": "Rutinitas", "uz": "Tartib", "ru": "Ритуал"},
    "new-season-muslimah-edit": {"en": "Edit", "id": "Pilihan", "uz": "Tanlov", "ru": "Подборка"},
}

EDITORIAL_TITLES = {
    "modest-styling-guide": {
        "en": "Modest Styling Guide", "id": "Panduan Gaya Muslimah",
        "uz": "Muslimona uslub qo'llanmasi", "ru": "Гид по скромному стилю",
    },
    "hijab-styling-guide": {
        "en": "Hijab Styling Guide", "id": "Panduan Gaya Hijab",
        "uz": "Hijob qo'llanmasi", "ru": "Гид по стилю хиджаба",
    },
    "tropical-halal-skincare-routine": {
        "en": "Tropical Halal Skincare Routine", "id": "Rutinitas Skincare Halal Tropis",
        "uz": "Tropik halol teri parvarishi tartibi", "ru": "Тропический халяль-уход: ритуал",
    },
    "new-season-muslimah-edit": {
        "en": "New Season Muslimah Edit", "id": "Pilihan Muslimah Musim Baru",
        "uz": "Yangi mavsum muslima tanlovi", "ru": "Мусульманская подборка нового сезона",
    },
}

EDITORIAL_DESCRIPTIONS = {
    "modest-styling-guide": {
        "en": "Simple ways to build an elegant modest wardrobe for every day.",
        "id": "Cara sederhana membangun lemari pakaian muslimah yang elegan untuk setiap hari.",
        "uz": "Har kun uchun nafis muslimona garderob yaratishning oddiy usullari.",
        "ru": "Простые способы собрать элегантный скромный гардероб на каждый день.",
    },
    "hijab-styling-guide": {
        "en": "From chiffon to jersey — find your perfect drape and color pairings.",
        "id": "Dari sifon hingga jersey — temukan jatuh kain dan padanan warna terbaikmu.",
        "uz": "Shifondan jerseygacha — mukammal mato va rang uyg'unligini toping.",
        "ru": "От шифона до джерси — подберите идеальную драпировку и сочетание цветов.",
    },
    "tropical-halal-skincare-routine": {
        "en": "A gentle halal routine made for warm, humid climates.",
        "id": "Rutinitas halal yang lembut untuk iklim hangat dan lembap.",
        "uz": "Iliq va nam iqlim uchun mo'rt halol parvarish tartibi.",
        "ru": "Мягкий халяль-ритуал для тёплого влажного климата.",
    },
    "new-season-muslimah-edit": {
        "en": "Flowing gamis, clean abayas, soft neutrals — this season's key silhouettes.",
        "id": "Gamis mengalir, abaya bersih, warna netral lembut — siluet utama musim ini.",
        "uz": "Oqimli gamislar, toza abayalar, yumshoq neytral ranglar — shu mavsumning asosiy siluetlari.",
        "ru": "Струящиеся гамисы, лаконичные абаи, мягкие нейтральные тона — ключевые силуэты сезона.",
    },
}

SECTION_KEYS = [
    "promo_bar", "hero", "categories", "best_sellers",
    "new_arrivals", "skincare", "daily_style", "stories", "footer",
]

SECTION_TITLES = {
    "promo_bar": {loc: "" for loc in LOCALES},
    "hero": {"en": "Curated fashion from Indonesia", "id": "Pilihan fashion dari Indonesia", "uz": "Indoneziyadan tanlangan moda", "ru": "Избранная мода из Индонезии"},
    "categories": {"en": "Shop by Department", "id": "Belanja berdasarkan Department", "uz": "Bo'lim bo'yicha xarid qiling", "ru": "Покупайте по отделам"},
    "best_sellers": {"en": "Best Sellers", "id": "Terlaris", "uz": "Eng ko‘p sotilganlar", "ru": "Бестселлеры"},
    "new_arrivals": {"en": "New Arrivals", "id": "Koleksi Terbaru", "uz": "Yangi kelganlar", "ru": "Новинки"},
    "skincare": {"en": "Skincare Essentials", "id": "Rawat Kulitmu", "uz": "Teri parvarishi", "ru": "Уход за кожей"},
    "daily_style": {"en": "Everyday Style", "id": "Gaya Sehari-hari", "uz": "Kundalik uslub", "ru": "Повседневный стиль"},
    "stories": {"en": "Stories & Guides", "id": "Cerita & Panduan", "uz": "Hikoyalar va qo'llanmalar", "ru": "Истории и гиды"},
    "footer": {loc: "" for loc in LOCALES},
}

HOMEPAGE_PRODUCT_SLUGS = {
    "best_sellers": (
        "smooth-cotton-crew-neck-sweater-4aa1f9",
        "mini-cable-crew-neck-cardigan-7f6c29",
        "skechers-d-lux-walker-3-0-5290c0",
        "safi-age-defy-sensitive-biome-calming-gel-45gr-a0ed8c",
    ),
    "new_arrivals": (
        "safi-acne-expert-acne-treatment-gel-bf9f7e",
        "safi-acne-expert-sebum-control-fluid-c0e878",
        "safi-acne-expert-clarifying-2-in-1-cleanser-4051de",
        "safi-age-defy-sensitive-biome-calming-gel-45gr-a0ed8c",
    ),
    "skincare": (
        "safi-age-defy-sensitive-biome-balancing-cleanser-100ml-b90220",
        "safi-acne-expert-sebum-control-fluid-c0e878",
        "safi-age-defy-sensitive-biome-soothing-serum-30ml-9ff972",
        "safi-age-defy-sensitive-biome-calming-gel-45gr-a0ed8c",
    ),
    "daily_style": (
        "smooth-cotton-crew-neck-sweater-97d9db",
        "light-souffle-yarn-relaxed-cardigan-7651f5",
        "pocketable-uv-protection-parka-water-repellent-nanodesign-0153f0",
        "utility-short-jacket-58a69a",
    ),
}

FOOTER_LINKS = {
    "shop": [
        ("footer.link.newArrivals", "/shop?badge=new"),
        ("footer.link.bestSellers", "/shop?badge=bestseller"),
    ],
    "help": [
        ("footer.link.contact", "/page/contact"),
        ("footer.link.shipping", "/page/shipping"),
        ("footer.link.returns", "/page/returns"),
        ("footer.link.faq", "/faq"),
    ],
    "account": [
        ("footer.link.myAccount", "/account"),
        ("header.wishlist", "/wishlist"),
        ("footer.link.orders", "/orders"),
    ],
    "about": [
        ("footer.link.aboutUs", "/page/about"),
        ("footer.link.privacy", "/page/privacy"),
        ("footer.link.terms", "/page/terms"),
    ],
}

FOOTER_GROUP_KEYS = {
    "shop": "footer.shop",
    "help": "footer.help",
    "account": "footer.account",
    "about": "footer.about",
}

NAV_ITEMS = [
    ("nav.newArrivals", "/shop?badge=new"),
    ("nav.bestSellers", "/shop?badge=bestseller"),
    ("nav.sale", "/shop?badge=sale"),
]

PAGES = {
    "about": {
        "en": ("About MUSLIMAH CANTIK", "MUSLIMAH CANTIK is a single-vendor boutique for modest fashion and tropical halal skincare, operated from Tashkent. We curate quality pieces and serve customers across Uzbekistan with UZS pricing."),
        "id": ("Tentang MUSLIMAH CANTIK", "MUSLIMAH CANTIK adalah butik vendor tunggal untuk busana muslimah dan skincare halal tropis, beroperasi dari Tashkent. Kami melayani pelanggan di seluruh Uzbekistan dengan harga UZS."),
        "uz": ("MUSLIMAH CANTIK haqida", "MUSLIMAH CANTIK — muslimona moda va tropik halol teri parvarishiga ixtisoslashgan yagona vendor butik. Toshkentdan butun O'zbekiston bo'ylab UZS narxlari bilan xizmat ko'rsatamiz."),
        "ru": ("О MUSLIMAH CANTIK", "MUSLIMAH CANTIK — монобрендовый бутик мусульманской моды и тропического халяль-ухода из Ташкента. Мы обслуживаем клиентов по всему Узбекистану с ценами в сумах."),
    },
    "contact": {
        "en": ("Contact Us", "Reach our team at contact@shanicantik.com. We reply within one business day."),
        "id": ("Hubungi Kami", "Hubungi tim kami di contact@shanicantik.com. Kami membalas dalam satu hari kerja."),
        "uz": ("Biz bilan bog'laning", "Jamoamizga contact@shanicantik.com orqali murojaat qiling. Bir ish kuni ichida javob beramiz."),
        "ru": ("Свяжитесь с нами", "Напишите нам: contact@shanicantik.com. Мы отвечаем в течение одного рабочего дня."),
    },
    "shipping": {
        "en": ("Shipping", "All products are pre-order. Estimated delivery is 2–3 weeks. Final shipping details are confirmed by our team."),
        "id": ("Pengiriman", "Semua produk adalah pre-order. Estimasi pengiriman 2–3 minggu. Detail pengiriman dikonfirmasi oleh tim kami."),
        "uz": ("Yetkazib berish", "Barcha mahsulotlar pre-order asosida. Yetkazib berish muddati taxminan 2–3 hafta. Yakuniy yetkazish tafsilotlarini jamoamiz tasdiqlaydi."),
        "ru": ("Доставка", "Все товары доступны по предзаказу. Ориентировочный срок доставки — 2–3 недели. Окончательные детали доставки подтверждает наша команда."),
    },
    "returns": {
        "en": ("Returns", "For return or exchange questions, contact our team after your pre-order is delivered. Eligibility is reviewed case by case."),
        "id": ("Pengembalian", "Untuk pertanyaan pengembalian atau penukaran, hubungi tim kami setelah pre-order diterima. Kelayakan ditinjau berdasarkan kasus."),
        "uz": ("Qaytarish", "Qaytarish yoki almashtirish bo'yicha savollar uchun pre-order qabul qilingandan so'ng jamoamizga murojaat qiling. Har bir holat alohida ko'rib chiqiladi."),
        "ru": ("Возврат", "По вопросам возврата или обмена свяжитесь с нашей командой после получения предзаказа. Каждый случай рассматривается отдельно."),
    },
    "privacy": {
        "en": ("Privacy Policy", "We store only the data required to process your orders, including contact and delivery details. Payment details are not collected while online checkout is unavailable."),
        "id": ("Kebijakan Privasi", "Kami hanya menyimpan data yang diperlukan untuk memproses pesanan, termasuk kontak dan alamat pengiriman. Data pembayaran tidak dikumpulkan selama checkout online belum tersedia."),
        "uz": ("Maxfiylik siyosati", "Biz buyurtmalarni qayta ishlash uchun zarur bo'lgan ma'lumotlarni, jumladan aloqa va yetkazish ma'lumotlarini saqlaymiz. Onlayn checkout mavjud bo'lmaganda to'lov ma'lumotlari yig'ilmaydi."),
        "ru": ("Политика конфиденциальности", "Мы храним только данные, необходимые для обработки заказов, включая контактные данные и адрес доставки. Пока онлайн-оформление недоступно, платёжные данные не собираются."),
    },
    "terms": {
        "en": ("Terms of Service", "By ordering from MUSLIMAH CANTIK you agree to our pricing in UZS and the shipping and returns terms published on this page. Online ordering is currently paused."),
        "id": ("Syarat Layanan", "Dengan memesan di MUSLIMAH CANTIK, Anda menyetujui harga dalam UZS serta ketentuan pengiriman dan pengembalian yang dipublikasikan di halaman ini. Pemesanan online sedang ditangguhkan."),
        "uz": ("Foydalanish shartlari", "MUSLIMAH CANTIK dan buyurtma berish orqali siz UZS narxlariga hamda bu sahifada e'lon qilingan yetkazish va qaytarish shartlariga rozilik bildirasiz. Onlayn buyurtma hozircha to'xtatilgan."),
        "ru": ("Условия использования", "Оформляя заказ в MUSLIMAH CANTIK, вы соглашаетесь с ценами в сумах и условиями доставки и возврата, опубликованными на этой странице. Онлайн-заказы временно приостановлены."),
    },
}

FAQ_ITEMS = [
    {
        "slug": "payment-methods",
        "q": {
            "en": "Which payment methods do you accept?",
            "id": "Metode pembayaran apa saja yang diterima?",
            "uz": "Qanday to'lov usullarini qabul qilasiz?",
            "ru": "Какие способы оплаты вы принимаете?",
        },
        "a": {
            "en": "Online payment is not available yet. Please contact our team if you have a question about a product.",
            "id": "Pembayaran online belum tersedia. Silakan hubungi tim kami jika Anda memiliki pertanyaan tentang produk.",
            "uz": "Onlayn to'lov hali mavjud emas. Mahsulot haqida savolingiz bo'lsa, jamoamizga murojaat qiling.",
            "ru": "Онлайн-оплата пока недоступна. Если у вас есть вопрос о товаре, свяжитесь с нашей командой.",
        },
    },
    {
        "slug": "shipping-time",
        "q": {
            "en": "How long does delivery take?",
            "id": "Berapa lama pengiriman?",
            "uz": "Yetkazib berish qancha vaqt oladi?",
            "ru": "Сколько занимает доставка?",
        },
        "a": {
            "en": "All products are pre-order with an estimated delivery time of 2–3 weeks.",
            "id": "Semua produk adalah pre-order dengan estimasi pengiriman 2–3 minggu.",
            "uz": "Barcha mahsulotlar pre-order asosida bo‘lib, yetkazib berish muddati taxminan 2–3 hafta.",
            "ru": "Все товары доступны по предзаказу, ориентировочный срок доставки — 2–3 недели.",
        },
    },
]


def _load_translations():
    """Extract {key: {locale: value}} from the frontend translations file."""
    if not Path(TRANSLATIONS_PATH).is_file():
        raise RuntimeError(
            f"Frontend translations file not found: {TRANSLATIONS_PATH}. "
            "Set FRONTEND_TRANSLATIONS_PATH when running the CMS seed from a container."
        )
    src = open(TRANSLATIONS_PATH, encoding="utf-8").read()
    out: dict = {}
    for locale in LOCALES:
        match = re.search(rf"\n  {locale}: \{{(.*?)\n  \}}", src, re.S)
        if not match:
            continue
        for key, value in re.findall(r'"([^"]+)":\s*"((?:[^"\\]|\\.)*)"', match.group(1)):
            out.setdefault(key, {})[locale] = value.replace('\\"', '"').replace("\\n", "\n")
    return out


def _tr(strings: dict, key: str, locale: str) -> str:
    return strings.get(key, {}).get(locale) or strings.get(key, {}).get("en") or ""


DEPARTMENT_VISUAL_SLUGS = (
    "women-muslimah",
    "uniqlo-products",
    "tropical-halal-skincare",
)


async def _seed_missing_department_visuals(session) -> int:
    """Expose linked generated department media as editable CMS entries."""
    categories = (
        await session.execute(
            select(Category).where(
                Category.kind == "department",
                Category.slug.in_(DEPARTMENT_VISUAL_SLUGS),
                Category.is_active.is_(True),
                Category.media_id.is_not(None),
            )
        )
    ).scalars().all()
    if not categories:
        return 0

    existing_slugs = set(
        (
            await session.execute(
                select(CmsContentEntry.slug).where(
                    CmsContentEntry.content_type == "department_visual",
                    CmsContentEntry.slug.in_([category.slug for category in categories]),
                )
            )
        ).scalars().all()
    )
    media_ids = [category.media_id for category in categories]
    media_translations = (
        await session.execute(
            select(CmsMediaTranslation).where(CmsMediaTranslation.media_id.in_(media_ids))
        )
    ).scalars().all()
    category_translations = (
        await session.execute(
            select(CategoryTranslation).where(
                CategoryTranslation.category_id.in_([category.id for category in categories])
            )
        )
    ).scalars().all()
    media_alt = {(item.media_id, item.locale): item.alt_text for item in media_translations}
    category_name = {
        (item.category_id, item.locale): item.name for item in category_translations
    }

    created = 0
    for category in categories:
        if category.slug in existing_slugs:
            continue
        english_name = category_name.get((category.id, "en")) or category.slug
        entry = CmsContentEntry(
            content_type="department_visual",
            internal_name=f"Homepage department: {english_name}",
            slug=category.slug,
            status="published",
            placement="homepage",
            sort_order=category.sort_order,
            is_visible=True,
            media_id=category.media_id,
            payload={},
        )
        session.add(entry)
        await session.flush()
        for locale in LOCALES:
            alt_text = (
                media_alt.get((category.media_id, locale))
                or category_name.get((category.id, locale))
                or english_name
            )
            session.add(
                CmsContentTranslation(
                    entry_id=entry.id,
                    locale=locale,
                    alt_text=alt_text[:255],
                )
            )
        existing_slugs.add(category.slug)
        created += 1
    return created


async def seed():
    strings = _load_translations()
    async with SessionLocal() as session:
        entries = (await session.execute(select(CmsContentEntry))).scalars().all()
        existing_entries = {
            (entry.content_type, entry.slug): entry for entry in entries
        }
        existing_translations = (
            await session.execute(select(CmsContentTranslation))
        ).scalars().all()
        translations_by_entry = {}
        for translation in existing_translations:
            translations_by_entry.setdefault(translation.entry_id, {})[
                translation.locale
            ] = translation
        if ("hero", "home-hero") in existing_entries:
            # Remove only legacy remote image fallbacks. CMS-linked/local media
            # remains authoritative and is never overwritten by a seed rerun.
            canonical_pages = {
                slug: {loc: {"title": value[0], "body": value[1]} for loc, value in content.items()}
                for slug, content in PAGES.items()
                if slug in {"shipping", "returns"}
            }
            canonical_faqs = {
                item["slug"]: {
                    loc: {"title": item["q"][loc], "body": item["a"][loc]}
                    for loc in LOCALES
                }
                for item in FAQ_ITEMS
                if item["slug"] == "shipping-time"
            }
            canonical_promos = {
                slug: {loc: {"title": "", "body": ""} for loc in LOCALES}
                for slug in ("top-bar", "footer-promo")
            }
            for entry in entries:
                payload = dict(entry.payload or {})
                image_url = payload.get("image_url")
                if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
                    payload.pop("image_url", None)
                    entry.payload = payload
                desired = (
                    canonical_pages.get(entry.slug)
                    or canonical_faqs.get(entry.slug)
                    or canonical_promos.get(entry.slug)
                )
                if desired:
                    by_locale = translations_by_entry.get(entry.id, {})
                    for locale, fields in desired.items():
                        translation = by_locale.get(locale)
                        if not translation:
                            continue
                        if translation.title != fields["title"] or translation.body != fields["body"]:
                            translation.title = fields["title"]
                            translation.body = fields["body"]
        created = 0

        async def add_entry(content_type, name, slug, translations, sort_order=0,
                            placement="", cta_url=None, secondary_cta_url=None,
                            payload=None, status="published", media_id=None):
            nonlocal created
            key = (content_type, slug)
            existing_entry = existing_entries.get(key)
            if existing_entry:
                entry_translations = translations_by_entry.setdefault(
                    existing_entry.id, {}
                )
                for locale, fields in translations.items():
                    if locale in entry_translations:
                        continue
                    translation = CmsContentTranslation(
                        entry_id=existing_entry.id, locale=locale, **fields
                    )
                    session.add(translation)
                    entry_translations[locale] = translation
                    created += 1
                return existing_entry

            entry = CmsContentEntry(
                content_type=content_type, internal_name=name, slug=slug,
                status=status, placement=placement, sort_order=sort_order,
                cta_url=cta_url, secondary_cta_url=secondary_cta_url,
                payload=payload or {}, media_id=media_id,
            )
            session.add(entry)
            await session.flush()
            for locale, fields in translations.items():
                translation = CmsContentTranslation(
                    entry_id=entry.id, locale=locale, **fields
                )
                session.add(translation)
                translations_by_entry.setdefault(entry.id, {})[locale] = translation
            created += 1
            existing_entries[key] = entry
            return entry

        # announcement bar
        await add_entry(
            "announcement", "Top announcement bar", "top-bar",
            {loc: {"title": _tr(strings, "announcement.text", loc)} for loc in LOCALES},
            sort_order=0, placement="top",
        )
        # Hero remains anchored to a real catalog product while the campaign
        # visual is a separately generated asset that preserves that product.
        hero_product_id = await session.scalar(
            select(Product.id)
            .where(Product.status == "active", Product.slug == "smooth-cotton-crew-neck-sweater-4aa1f9")
            .limit(1)
        )
        if not hero_product_id:
            hero_product_id = await session.scalar(
                select(Product.id)
                .where(Product.status == "active")
                .order_by(Product.featured.desc(), Product.created_at.desc(), Product.id.desc())
                .limit(1)
            )
        hero_media = await session.scalar(
            select(CmsMediaAsset)
            .where(CmsMediaAsset.original_filename == "home-hero.jpg")
            .order_by(CmsMediaAsset.created_at.desc(), CmsMediaAsset.id.desc())
            .limit(1)
        )
        await add_entry(
            "hero", "Homepage hero", "home-hero",
            {
                loc: {
                    "eyebrow": _tr(strings, "brand.tagline", loc),
                    "title": _tr(strings, "page.home.heroTitle", loc),
                    "subtitle": _tr(strings, "page.home.heroSubtitle", loc),
                    "cta_label": _tr(strings, "home.shopNow", loc),
                    "secondary_cta_label": _tr(strings, "home.allDepartments", loc),
                }
                for loc in LOCALES
            },
            cta_url="/shop", secondary_cta_url="/shop",
            payload={"product_id": hero_product_id} if hero_product_id else {},
            media_id=hero_media.id if hero_media else None,
        )

        catalog_product_ids = {
            slug: product_id
            for product_id, slug in (
                await session.execute(
                    select(Product.id, Product.slug).where(
                        Product.status == "active",
                        Product.slug.in_(
                            [slug for slugs in HOMEPAGE_PRODUCT_SLUGS.values() for slug in slugs]
                        ),
                    )
                )
            ).all()
        }

        # homepage sections (visibility/order)
        for idx, key in enumerate(SECTION_KEYS):
            payload = {}
            if key in HOMEPAGE_PRODUCT_SLUGS:
                slugs = HOMEPAGE_PRODUCT_SLUGS[key]
                product_ids = [catalog_product_ids[slug] for slug in slugs if slug in catalog_product_ids]
                payload = {"source": "catalog", "product_ids": product_ids, "limit": 4}
            await add_entry(
                "homepage_section", f"Section: {key}", key,
                {loc: {"title": SECTION_TITLES[key][loc]} for loc in LOCALES},
                sort_order=idx, payload=payload,
                status="draft" if key == "promo_bar" else "published",
            )
        # stories & guides
        for idx, slug in enumerate(EDITORIAL_SLUGS):
            await add_entry(
                "story", f"Story: {slug}", slug,
                {
                    loc: {
                        "eyebrow": EDITORIAL_LABELS[slug].get(loc, ""),
                        "title": EDITORIAL_TITLES[slug].get(loc, ""),
                        "description": EDITORIAL_DESCRIPTIONS[slug].get(loc, ""),
                        "cta_label": _tr(strings, "editorial.cta", loc),
                    }
                    for loc in LOCALES
                },
                sort_order=idx, cta_url="/shop",
                payload={},
            )
        # stories section title
        await add_entry(
            "footer_text", "Stories section title", "stories-title",
            {loc: {"title": _tr(strings, "editorial.title", loc)} for loc in LOCALES},
            placement="home_stories",
        )
        # footer promo line
        await add_entry(
            "footer_text", "Footer promo", "footer-promo",
            {loc: {"title": _tr(strings, "footer.promo", loc)} for loc in LOCALES},
            placement="footer", sort_order=10,
        )
        # footer groups + items
        for g_idx, (group_slug, key) in enumerate(FOOTER_GROUP_KEYS.items()):
            await add_entry(
                "footer_group", f"Footer group {group_slug}", group_slug,
                {loc: {"title": _tr(strings, key, loc)} for loc in LOCALES},
                sort_order=g_idx, placement="footer",
            )
            for i_idx, (label_key, url) in enumerate(FOOTER_LINKS[group_slug]):
                await add_entry(
                    "footer_item", f"Footer link {label_key}", f"{group_slug}-{i_idx}",
                    {loc: {"title": _tr(strings, label_key, loc)} for loc in LOCALES},
                    sort_order=i_idx, placement="footer", cta_url=url,
                    payload={"group": group_slug},
                )
        # secondary navigation items (fixed 3 departments stay catalog-driven)
        for n_idx, (label_key, url) in enumerate(NAV_ITEMS):
            await add_entry(
                "nav_item", f"Nav {label_key}", f"secondary-{n_idx}",
                {loc: {"title": _tr(strings, label_key, loc)} for loc in LOCALES},
                sort_order=n_idx, placement="secondary", cta_url=url,
            )
        # informational pages
        for p_idx, (slug, content) in enumerate(PAGES.items()):
            await add_entry(
                "page", f"Page: {slug}", slug,
                {loc: {"title": content[loc][0], "body": content[loc][1]} for loc in LOCALES},
                sort_order=p_idx,
            )
        # FAQ
        for f_idx, item in enumerate(FAQ_ITEMS):
            await add_entry(
                "faq_item", f"FAQ: {item['slug']}", item["slug"],
                {loc: {"title": item["q"][loc], "body": item["a"][loc]} for loc in LOCALES},
                sort_order=f_idx,
            )

        created += await _seed_missing_department_visuals(session)
        await session.commit()
        print(f"cms seed: ensured defaults; created {created} entries/translations")


if __name__ == "__main__":
    asyncio.run(seed())
