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

from db.models import CmsContentEntry, CmsContentTranslation
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
    "promo_bar", "hero", "categories", "new_arrivals",
    "departments", "best_sellers", "stories", "footer",
]

FOOTER_LINKS = {
    "shop": [
        ("footer.link.newArrivals", "/shop?badge=new"),
        ("footer.link.bestSellers", "/shop?badge=bestseller"),
        ("nav.womenMuslimah", "/shop?department=women-muslimah"),
        ("nav.uniqloProducts", "/shop?department=uniqlo-products"),
        ("nav.skincare", "/shop?department=tropical-halal-skincare"),
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
        "en": ("About MUSLIMAH CANTIK", "MUSLIMAH CANTIK is a single-vendor boutique for modest fashion and tropical halal skincare, operated from Tashkent. We curate quality pieces and serve customers across Uzbekistan with CLICK payments and UZS pricing."),
        "id": ("Tentang MUSLIMAH CANTIK", "MUSLIMAH CANTIK adalah butik vendor tunggal untuk busana muslimah dan skincare halal tropis, beroperasi dari Tashkent. Kami melayani pelanggan di seluruh Uzbekistan dengan pembayaran CLICK dan harga UZS."),
        "uz": ("MUSLIMAH CANTIK haqida", "MUSLIMAH CANTIK — muslimona moda va tropik halol teri parvarishiga ixtisoslashgan yagona vendor butik. Toshkentdan butun O'zbekiston bo'ylab CLICK to'lovi va UZS narxlari bilan xizmat ko'rsatamiz."),
        "ru": ("О MUSLIMAH CANTIK", "MUSLIMAH CANTIK — монобрендовый бутик мусульманской моды и тропического халяль-ухода из Ташкента. Мы обслуживаем клиентов по всему Узбекистану с оплатой CLICK и ценами в сумах."),
    },
    "contact": {
        "en": ("Contact Us", "Reach our team at official@muslimahcantik.id. We reply within one business day."),
        "id": ("Hubungi Kami", "Hubungi tim kami di official@muslimahcantik.id. Kami membalas dalam satu hari kerja."),
        "uz": ("Biz bilan bog'laning", "Jamoamizga official@muslimahcantik.id orqali murojaat qiling. Bir ish kuni ichida javob beramiz."),
        "ru": ("Свяжитесь с нами", "Напишите нам: official@muslimahcantik.id. Мы отвечаем в течение одного рабочего дня."),
    },
    "shipping": {
        "en": ("Shipping", "We ship across Uzbekistan. Standard delivery (3-5 business days) is 30,000 UZS and free for orders over 550,000 UZS. Express delivery (1-2 business days) is 65,000 UZS."),
        "id": ("Pengiriman", "Kami mengirim ke seluruh Uzbekistan. Pengiriman standar (3-5 hari kerja) 30.000 UZS, gratis untuk pesanan di atas 550.000 UZS. Ekspres (1-2 hari kerja) 65.000 UZS."),
        "uz": ("Yetkazib berish", "Butun O'zbekiston bo'ylab yetkazamiz. Standart (3-5 ish kuni) — 30 000 so'm, 550 000 so'mdan yuqori buyurtmalarga bepul. Ekspress (1-2 ish kuni) — 65 000 so'm."),
        "ru": ("Доставка", "Доставляем по всему Узбекистану. Стандартная (3-5 рабочих дней) — 30 000 сум, бесплатно при заказе от 550 000 сум. Экспресс (1-2 рабочих дня) — 65 000 сум."),
    },
    "returns": {
        "en": ("Returns", "Unused items in original packaging can be returned within 14 days of delivery. Contact us to start a return."),
        "id": ("Pengembalian", "Produk yang belum dipakai dalam kemasan asli dapat dikembalikan dalam 14 hari setelah diterima. Hubungi kami untuk memulai pengembalian."),
        "uz": ("Qaytarish", "Ishlatilmagan, original qadoqdagi mahsulotlarni yetkazilgandan keyin 14 kun ichida qaytarish mumkin. Qaytarish uchun bizga yozing."),
        "ru": ("Возврат", "Неиспользованные товары в оригинальной упаковке можно вернуть в течение 14 дней после доставки. Свяжитесь с нами для оформления возврата."),
    },
    "privacy": {
        "en": ("Privacy Policy", "We store only the data required to process your orders (contact and delivery details). Payment data is processed by CLICK; we never see or store card data."),
        "id": ("Kebijakan Privasi", "Kami hanya menyimpan data yang diperlukan untuk memproses pesanan Anda (kontak dan alamat pengiriman). Data pembayaran diproses oleh CLICK; kami tidak pernah melihat atau menyimpan data kartu."),
        "uz": ("Maxfiylik siyosati", "Biz faqat buyurtmalaringizni qayta ishlash uchun zarur ma'lumotlarni saqlaymiz (aloqa va yetkazish ma'lumotlari). To'lov ma'lumotlarini CLICK qayta ishlaydi; biz karta ma'lumotlarini ko'rmaymiz va saqlamaymiz."),
        "ru": ("Политика конфиденциальности", "Мы храним только данные, необходимые для обработки заказов (контакты и адрес доставки). Платёжные данные обрабатывает CLICK; мы не видим и не храним данные карт."),
    },
    "terms": {
        "en": ("Terms of Service", "By ordering from MUSLIMAH CANTIK you agree to our pricing in UZS, CLICK payment processing, and the shipping/returns terms published on this page."),
        "id": ("Syarat Layanan", "Dengan memesan di MUSLIMAH CANTIK, Anda menyetujui harga dalam UZS, pemrosesan pembayaran CLICK, serta ketentuan pengiriman/pengembalian yang dipublikasikan di halaman ini."),
        "uz": ("Foydalanish shartlari", "MUSLIMAH CANTIK dan buyurtma berish orqali siz UZS narxlariga, CLICK to'lov qayta ishlashga va bu sahifada e'lon qilingan yetkazish/qaytarish shartlariga rozilik bildirasiz."),
        "ru": ("Условия использования", "Оформляя заказ в MUSLIMAH CANTIK, вы соглашаетесь с ценами в сумах, обработкой платежей CLICK и условиями доставки/возврата, опубликованными на этой странице."),
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
            "en": "We accept CLICK payments in UZS. Card details are processed securely by CLICK.",
            "id": "Kami menerima pembayaran CLICK dalam UZS. Data kartu diproses dengan aman oleh CLICK.",
            "uz": "Biz UZS da CLICK to'lovlarini qabul qilamiz. Karta ma'lumotlari CLICK tomonidan xavfsiz qayta ishlanadi.",
            "ru": "Мы принимаем оплату через CLICK в сумах. Данные карт безопасно обрабатываются CLICK.",
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
            "en": "Standard delivery takes 3-5 business days; express takes 1-2 business days within Uzbekistan.",
            "id": "Pengiriman standar 3-5 hari kerja; ekspres 1-2 hari kerja di seluruh Uzbekistan.",
            "uz": "Standart yetkazish 3-5 ish kuni; ekspress 1-2 ish kuni O'zbekiston bo'ylab.",
            "ru": "Стандартная доставка — 3-5 рабочих дней; экспресс — 1-2 рабочих дня по Узбекистану.",
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
            for entry in entries:
                payload = dict(entry.payload or {})
                image_url = payload.get("image_url")
                if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
                    payload.pop("image_url", None)
                    entry.payload = payload
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
        # hero
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
            payload={},
        )
        # homepage sections (visibility/order)
        for idx, key in enumerate(SECTION_KEYS):
            await add_entry("homepage_section", f"Section: {key}", key,
                            {loc: {"title": key.replace("_", " ").title()} for loc in LOCALES},
                            sort_order=idx)
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
