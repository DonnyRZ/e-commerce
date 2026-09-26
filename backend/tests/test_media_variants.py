from pathlib import Path

from PIL import Image

from cms.media_variants import create_webp_variant


def test_webp_variant_is_resized_and_reused(tmp_path: Path):
    source = tmp_path / "product.png"
    Image.new("RGB", (1600, 800), (20, 80, 60)).save(source)

    variant_path = Path(create_webp_variant(str(source), 640))
    assert variant_path.is_file()
    with Image.open(variant_path) as variant:
        assert variant.format == "WEBP"
        assert variant.size == (640, 320)

    assert create_webp_variant(str(source), 640) == str(variant_path)
    assert len(list((tmp_path / ".variants").glob("*.webp"))) == 1


def test_webp_variant_does_not_upscale_and_preserves_transparency(tmp_path: Path):
    source = tmp_path / "transparent.png"
    Image.new("RGBA", (80, 40), (20, 80, 60, 120)).save(source)

    variant_path = Path(create_webp_variant(str(source), 640))
    with Image.open(variant_path) as variant:
        assert variant.size == (80, 40)
        assert variant.mode == "RGBA"
        assert variant.getpixel((0, 0))[3] == 120
