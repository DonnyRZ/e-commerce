"""Idempotent seed: migrate the approved hardcoded storefront content into
the CMS (draft->published), so the storefront can switch to CMS authority
without any visual change.

Reads the 4-locale strings straight from the frontend translations file to
avoid duplicating content. Skips entirely if CMS entries already exist.
"""

import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import func, select

from db.models import CmsContentEntry, CmsContentTranslation, Product
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
    "promo_bar", "hero", "categories", "curated_primary",
    "curated_secondary", "stories", "footer",
]

SECTION_TITLES = {
    "promo_bar": {loc: "" for loc in LOCALES},
    "hero": {"en": "Curated fashion from Indonesia", "id": "Pilihan fashion dari Indonesia", "uz": "Indoneziyadan tanlangan moda", "ru": "Избранная мода из Индонезии"},
    "categories": {"en": "Shop by Department", "id": "Belanja berdasarkan Department", "uz": "Bo'lim bo'yicha xarid qiling", "ru": "Покупайте по отделам"},
    "curated_primary": {"en": "Picks for you", "id": "Pilihan untukmu", "uz": "Siz uchun tanlovlar", "ru": "Подборка для вас"},
    "curated_secondary": {"en": "Curated collection", "id": "Koleksi pilihan", "uz": "Tanlangan kolleksiya", "ru": "Избранная коллекция"},
    "stories": {"en": "Stories & Guides", "id": "Cerita & Panduan", "uz": "Hikoyalar va qo'llanmalar", "ru": "Истории и гиды"},
    "footer": {loc: "" for loc in LOCALES},
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


async def seed():
    strings = _load_translations()
    async with SessionLocal() as session:
        existing = await session.scalar(select(func.count(CmsContentEntry.id)))
        if existing:
            # Remove only legacy remote image fallbacks. CMS-linked/local media
            # remains authoritative and is never overwritten by a seed rerun.
            entries = (await session.execute(select(CmsContentEntry))).scalars().all()
            changed = False
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
                    changed = True
                desired = (
                    canonical_pages.get(entry.slug)
                    or canonical_faqs.get(entry.slug)
                    or canonical_promos.get(entry.slug)
                )
                if desired:
                    translations = (
                        await session.execute(
                            select(CmsContentTranslation).where(
                                CmsContentTranslation.entry_id == entry.id
                            )
                        )
                    ).scalars().all()
                    by_locale = {translation.locale: translation for translation in translations}
                    for locale, fields in desired.items():
                        translation = by_locale.get(locale)
                        if not translation:
                            continue
                        if translation.title != fields["title"] or translation.body != fields["body"]:
                            translation.title = fields["title"]
                            translation.body = fields["body"]
                            changed = True
            if changed:
                await session.commit()
            print("cms seed: entries already exist, skipping (idempotent)")
            return

        created = 0

        async def add_entry(content_type, name, slug, translations, sort_order=0,
                            placement="", cta_url=None, secondary_cta_url=None,
                            payload=None, status="published"):
            nonlocal created
            entry = CmsContentEntry(
                content_type=content_type, internal_name=name, slug=slug,
                status=status, placement=placement, sort_order=sort_order,
                cta_url=cta_url, secondary_cta_url=secondary_cta_url,
                payload=payload or {},
            )
            session.add(entry)
            await session.flush()
            for locale, fields in translations.items():
                session.add(CmsContentTranslation(entry_id=entry.id, locale=locale, **fields))
            created += 1
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
            payload={
                "product_id": hero_product_id,
                "hero_asset_url": "/brand/generated/home-hero-smooth-cotton-collection.png",
                "hero_mobile_asset_url": "/brand/generated/home-hero-smooth-cotton-mobile.png",
            } if hero_product_id else {},
        )
        # homepage sections (visibility/order)
        for idx, key in enumerate(SECTION_KEYS):
            payload = {}
            if key == "curated_primary":
                payload = {"source": "catalog", "sort": "newest", "limit": 8}
            elif key == "curated_secondary":
                payload = {"source": "catalog", "sort": "featured", "limit": 8}
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

        await session.commit()
        print(f"cms seed: created {created} published entries")


if __name__ == "__main__":
    asyncio.run(seed())
