"""Small, cached WebP derivatives for media used in image-heavy UI cards."""

import os
import threading
import uuid
from pathlib import Path


SUPPORTED_WIDTHS = frozenset({320, 480, 640, 960, 1280, 1920})
_VARIANT_LOCK = threading.Lock()


def create_webp_variant(source_path: str, width: int) -> str:
    """Create or reuse an immutable, width-limited WebP derivative."""

    source = Path(source_path)
    variant_dir = source.parent / ".variants"
    variant_path = variant_dir / f"{source.name}.w{width}.webp"

    with _VARIANT_LOCK:
        if variant_path.is_file():
            return str(variant_path)

        from PIL import Image, ImageOps

        variant_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = variant_dir / f".{variant_path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with Image.open(source) as original:
                if getattr(original, "is_animated", False):
                    original.seek(0)
                image = ImageOps.exif_transpose(original)
                if image.width > width:
                    height = max(1, round(image.height * width / image.width))
                    image = image.resize((width, height), Image.Resampling.LANCZOS)

                has_alpha = (
                    "A" in image.getbands()
                    or (image.mode == "P" and "transparency" in image.info)
                )
                image = image.convert("RGBA" if has_alpha else "RGB")
                image.save(temporary_path, format="WEBP", quality=84, method=4)
            os.replace(temporary_path, variant_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    return str(variant_path)
