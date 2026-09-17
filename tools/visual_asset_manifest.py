"""Build the deterministic visual-asset manifest for the CMS import.

The generated files are intentionally not committed. This manifest is the
contract between image generation, CMS upload, and catalog mapping.
"""

from __future__ import annotations

import json
from pathlib import Path


LOCALES = ("id", "en", "uz", "ru")

PRODUCTS = [
    ("gray-sweat-oversized-full-zip-hoodie", "oversized full-zip cotton fleece hoodie", "gray, black, beige, and navy colorways", "apparel"),
    ("essential-crewneck-sweatshirt", "clean regular-fit cotton fleece crewneck sweatshirt", "off-white, gray, and black colorways", "apparel"),
    ("wide-leg-relaxed-trousers", "fluid wide-leg relaxed rayon-blend trousers", "black and beige colorways", "apparel"),
    ("premium-chiffon-hijab", "lightweight premium chiffon and voal hijab with elegant drape", "black, navy, beige, and maroon colorways", "apparel"),
    ("gamis-a-line-dress", "flowing A-line gamis dress in soft crepe", "dusty purple and beige colorways", "apparel"),
    ("abaya-classic-black", "timeless straight-cut classic abaya in premium nida fabric", "deep black colorway", "apparel"),
    ("mukena-travel-set", "compact travel mukena prayer-wear set with a matching pouch", "white and dusty pink colorways", "apparel"),
    ("kids-muslimah-daily-set", "comfortable modest daily set for a child, shown on a simple child-size mannequin", "soft neutral color palette", "apparel"),
    ("halal-gentle-facial-wash", "minimal unbranded gentle facial-wash bottle for all skin types", "clear and warm amber product materials", "skincare"),
    ("brightening-serum-30ml", "minimal unbranded 30 ml brightening serum dropper bottle", "clear glass, pale serum, and warm amber accents", "skincare"),
    ("tropical-moist-cream-50ml", "minimal unbranded 50 ml rich moisturizing cream jar", "ivory cream, clear glass, and warm amber accents", "skincare"),
    ("halal-daily-sunscreen-spf50", "minimal unbranded lightweight sunscreen tube for tropical daylight", "ivory tube with restrained emerald cap", "skincare"),
]

VARIANTS = [
    ("GSOZH-GRY", "gray hoodie", "hoodie", "gray"),
    ("GSOZH-BLK", "black hoodie", "hoodie", "black"),
    ("GSOZH-BGE", "beige hoodie", "hoodie", "beige"),
    ("GSOZH-NVY", "navy hoodie", "hoodie", "deep navy"),
    ("ECSW-OWH", "off-white crewneck", "crewneck sweatshirt", "off-white"),
    ("ECSW-GRY", "gray crewneck", "crewneck sweatshirt", "gray"),
    ("ECSW-BLK", "black crewneck", "crewneck sweatshirt", "black"),
    ("WLRT-BLK", "black wide-leg trousers", "wide-leg trousers", "black"),
    ("WLRT-BGE", "beige wide-leg trousers", "wide-leg trousers", "beige"),
    ("PCH-BLK-VOL", "black voal hijab", "hijab", "black"),
    ("PCH-NVY-VOL", "navy voal hijab", "hijab", "deep navy"),
    ("PCH-BGE-CHF", "beige chiffon hijab", "hijab", "beige"),
    ("PCH-MRN-CHF", "maroon chiffon hijab", "hijab", "deep maroon"),
    ("GALD-DPL", "dusty purple A-line gamis", "gamis dress", "dusty purple"),
    ("GALD-BGE", "beige A-line gamis", "gamis dress", "beige"),
    ("ACBK-BLK", "classic black abaya", "abaya", "deep black"),
    ("MTS-WHT", "white travel mukena", "mukena set", "white"),
    ("MTS-DPK", "dusty pink travel mukena", "mukena set", "dusty pink"),
]

TAXONOMY = [
    ("department", "women-muslimah", "a curated collection of flowing modest womenswear, hijabs, abayas, and prayer wear"),
    ("department", "uniqlo-products", "a calm collection of everyday minimal basics, cotton fleece, knitwear, and relaxed essentials"),
    ("department", "tropical-halal-skincare", "a refined halal skincare ritual with unbranded glass bottles, cream jars, and botanical accents"),
    ("category", "hijab-kerudung", "a neatly arranged premium hijab in soft chiffon with an elegant drape"),
    ("category", "gamis", "a flowing modest A-line gamis silhouette on a faceless mannequin"),
    ("category", "abaya", "a clean straight-cut abaya silhouette on a faceless mannequin"),
    ("category", "tunik", "a long modest tunic with refined soft drape on a faceless mannequin"),
    ("category", "blouse-muslimah", "a modest long-sleeve blouse with delicate fabric texture on a faceless mannequin"),
    ("category", "dress-muslimah", "a flowing modest dress silhouette on a faceless mannequin"),
    ("category", "setelan-muslimah", "a coordinated modest two-piece set folded and lightly draped"),
    ("category", "outer-muslimah", "an elegant long modest outer layer with a calm tailored silhouette"),
    ("category", "rok-muslimah", "a fluid modest long skirt with soft folds"),
    ("category", "celana-muslimah", "relaxed modest wide-leg trousers with a fluid drape"),
    ("category", "mukena", "a neatly folded prayer-wear mukena with a matching travel pouch"),
    ("category", "busana-syari", "a graceful full-coverage modest silhouette with flowing layers"),
    ("category", "busana-muslimah-kerja", "a polished modest workwear capsule with tailored neutrals"),
    ("category", "busana-muslimah-pesta", "an elevated modest occasionwear silhouette with subtle gold detail"),
    ("category", "busana-muslimah-hamil-menyusui", "a comfortable modest maternity and nursing silhouette"),
    ("category", "busana-muslimah-olahraga", "breathable modest activewear with clean athletic lines"),
    ("category", "busana-muslimah-anak", "a comfortable child-size modest outfit on a simple faceless mannequin"),
    ("category", "outerwear", "a minimal everyday outerwear piece with clean cotton texture"),
    ("category", "tshirts-sweats-fleece", "folded cotton tees, sweats, and fleece basics in soft neutrals"),
    ("category", "sweatshirts-hoodies", "a premium cotton fleece hoodie and crewneck folded neatly"),
    ("category", "bottoms", "relaxed everyday trousers and bottoms with fluid fabric folds"),
    ("category", "shirts-blouses", "a minimal long-sleeve shirt and blouse capsule"),
    ("category", "sweaters-knitwear", "a soft knitwear piece with visible woven texture"),
    ("category", "dresses-skirts", "a calm capsule of flowing dresses and long skirts"),
    ("category", "loungewear-home", "soft comfortable loungewear folded on a warm ivory surface"),
    ("category", "facial-wash", "an unbranded gentle facial-wash bottle with a clean bathroom-studio still life"),
    ("category", "moist-cream", "an unbranded moisturizing cream jar beside a soft botanical sprig"),
    ("category", "sunscreen", "an unbranded sunscreen tube in a bright tropical-studio still life"),
    ("category", "serum", "an unbranded serum dropper bottle with a clear glass and botanical still life"),
    ("category", "face-mist", "an unbranded facial mist bottle with fine water droplets and clean glass"),
]

EDITORIAL = [
    ("cms:hero:home-hero", "home-hero", "website hero composition for modest fashion and halal skincare, broad negative space on the left for CMS headline copy"),
    ("cms:story:modest-styling-guide", "modest-styling-guide", "editorial still life showing coordinated modest wardrobe textures and a folded hijab, composed with safe text space"),
    ("cms:story:hijab-styling-guide", "hijab-styling-guide", "editorial close-up of chiffon, voal, and soft jersey hijab folds in complementary neutral colors, safe text space"),
    ("cms:story:tropical-halal-skincare-routine", "tropical-halal-skincare-routine", "editorial halal skincare ritual with unbranded bottles, cream jar, water glass, and subtle tropical leaves, safe text space"),
    ("cms:story:new-season-muslimah-edit", "new-season-muslimah-edit", "editorial seasonal modest-fashion edit with a flowing gamis, clean abaya, and soft neutral fabrics, safe text space"),
]


def _alt(label: str) -> dict[str, str]:
    return {
        "id": label,
        "en": label,
        "uz": label,
        "ru": label,
    }


def _base_prompt(subject: str, *, product: bool = False, editorial: bool = False) -> str:
    framing = (
        "wide editorial composition with generous negative space and safe text area, no cropping"
        if editorial
        else "centered e-commerce composition with generous safe padding, no cropping"
    )
    return (
        "Use the MUSLIMAH CANTIK visual anchor only for art direction: seamless warm ivory background, "
        "soft diffused studio light, restrained emerald #02422C and warm gold #CD9B3A accents, warm neutral shadows. "
        f"Create {subject}. "
        f"Use {framing}. "
        "Premium realistic e-commerce campaign photography, accurate fabric/material detail, calm modest luxury. "
        + ("No identifiable face; if a mannequin or model is needed, show only a faceless mannequin or crop below the neck. " if product else "")
        + "No text, no watermark, no logo, no label, no brand mark, no fake typography, no product claims, "
        "no extra objects, no busy background, no distortion, no cut-off edges, no harsh reflections."
    )


def build_manifest() -> list[dict]:
    entries: list[dict] = []
    for slug, subject, colors, kind in PRODUCTS:
        for index in range(1, 5):
            role = [
                "primary three-quarter product view",
                "secondary three-quarter detail view",
                "material and construction detail still life",
                "quiet lifestyle/catalog composition without an identifiable face",
            ][index - 1]
            entries.append(
                {
                    "asset_key": f"product:{slug}:gallery:{index}",
                    "filename": f"product-{slug}-gallery-{index}.png",
                    "entity_type": "product",
                    "entity_slug": slug,
                    "role": "gallery",
                    "sort_order": index - 1,
                    "locale_alt": _alt(f"{slug} product image {index}"),
                    "prompt": _base_prompt(f"a product catalog image of {subject}; {colors}; {role}", product=True),
                }
            )
    for prefix, label, subject, color in VARIANTS:
        sku_prefix = prefix
        entries.append(
            {
                "asset_key": f"variant:{sku_prefix}",
                "filename": f"variant-{sku_prefix.lower()}.png",
                "entity_type": "variant",
                "entity_sku_prefix": sku_prefix,
                "role": "variant",
                "sort_order": 0,
                "locale_alt": _alt(f"{label} variant image"),
                "prompt": _base_prompt(
                    f"a single product variant image of a {subject} in exact {color} color, shown clearly against the studio set",
                    product=True,
                ),
            }
        )
    for kind, slug, subject in TAXONOMY:
        entries.append(
            {
                "asset_key": f"{kind}:{slug}",
                "filename": f"{kind}-{slug}.png",
                "entity_type": kind,
                "entity_slug": slug,
                "role": "taxonomy",
                "sort_order": 0,
                "locale_alt": _alt(f"{slug} collection image"),
                "prompt": _base_prompt(subject, product=True),
            }
        )
    for asset_key, slug, subject in EDITORIAL:
        entries.append(
            {
                "asset_key": asset_key,
                "filename": f"{slug}.png",
                "entity_type": "cms",
                "entity_slug": slug,
                "role": "hero" if "hero:" in asset_key else "editorial",
                "sort_order": 0,
                "locale_alt": _alt(f"{slug} editorial image"),
                "prompt": _base_prompt(subject, editorial=True),
            }
        )
    return entries


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "artifacts" / "imagegen" / "manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = build_manifest()
    output.write_text(json.dumps({"version": 1, "count": len(entries), "entries": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(entries)} entries to {output}")
