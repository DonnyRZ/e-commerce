"""Create deterministic web derivatives from the supplied brand mark.

The source artwork is never modified. The script only trims transparent
canvas noise, adds a safe symmetric margin, and exports browser-sized PNGs
plus a simple social preview card.

Usage:
    python ops/generate_brand_assets.py \
      --source "C:/path/to/logo.png" \
      --output frontend/public/brand
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


GREEN = (2, 66, 44, 255)
GOLD = (205, 155, 58, 255)
IVORY = (253, 247, 233, 255)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        (Path("C:/Windows/Fonts/georgiab.ttf") if bold else Path("C:/Windows/Fonts/georgia.ttf")),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def normalized_mark(source: Path, canvas_size: int = 1400) -> Image.Image:
    image = Image.open(source).convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        image = image.crop(bbox)

    safe_margin = round(canvas_size * 0.06)
    content_size = canvas_size - (safe_margin * 2)
    scale = min(content_size / image.width, content_size / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    canvas.alpha_composite(
        resized,
        ((canvas_size - resized.width) // 2, (canvas_size - resized.height) // 2),
    )
    return canvas


def create_social_preview(mark: Image.Image, output: Path) -> None:
    width, height = 1200, 630
    card = Image.new("RGBA", (width, height), IVORY)
    draw = ImageDraw.Draw(card)

    # A restrained border and divider make the preview feel intentional while
    # keeping the supplied mark as the visual focus.
    draw.rounded_rectangle((18, 18, width - 18, height - 18), radius=24, outline=GOLD, width=3)
    draw.line((510, 130, 510, height - 130), fill=GOLD, width=2)

    mark_size = 350
    mark_thumb = mark.resize((mark_size, mark_size), Image.Resampling.LANCZOS)
    card.alpha_composite(mark_thumb, (92, (height - mark_size) // 2))

    title = "MUSLIMAH CANTIK"
    title_x = 565
    max_title_width = width - title_x - 72
    title_size = 58
    title_font = _font(title_size, bold=True)
    while draw.textbbox((0, 0), title, font=title_font)[2] > max_title_width and title_size > 36:
        title_size -= 2
        title_font = _font(title_size, bold=True)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    title_y = (height - (title_box[3] - title_box[1])) // 2
    draw.text((title_x, title_y), title, font=title_font, fill=GREEN)
    draw.line((title_x, title_y - 24, title_x + 116, title_y - 24), fill=GOLD, width=5)
    card.convert("RGB").save(output, optimize=True, quality=94)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.source.is_file():
        raise SystemExit(f"Source logo not found: {args.source}")
    args.output.mkdir(parents=True, exist_ok=True)

    mark = normalized_mark(args.source)
    mark.save(args.output / "logo-mark.png", optimize=True)
    for size in (64, 128, 256, 512):
        mark.resize((size, size), Image.Resampling.LANCZOS).save(
            args.output / f"logo-mark-{size}.png", optimize=True
        )
    mark.resize((64, 64), Image.Resampling.LANCZOS).save(
        args.output / "favicon.png", optimize=True
    )
    mark.resize((180, 180), Image.Resampling.LANCZOS).save(
        args.output / "apple-touch-icon.png", optimize=True
    )
    create_social_preview(mark, args.output / "og-image.png")


if __name__ == "__main__":
    main()
