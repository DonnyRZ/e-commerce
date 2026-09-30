import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/size-tests")
os.environ.setdefault("JWT_SECRET", "isolated-size-test-secret-never-used-for-auth")

from fastapi import HTTPException
from product_sizes import (
    department_requires_size_selection,
    size_variant_is_visible,
    variants_have_required_size,
)
from routers.admin import _validate_product_sizes, router as admin_router


class ProductSizeBehaviorTests(unittest.TestCase):
    def test_legacy_presets_do_not_hide_or_reject_any_size(self):
        old_preset = {
            "applied_clothing": ["M", "L", "XL", "XXL"],
            "applied_footwear": ["36", "37", "38", "39", "40"],
        }
        for department, options in (
            ("women-muslimah", {"size": "S"}),
            ("batik", {"size": "XXXL"}),
            ("shoe", {"size": "42"}),
            ("uniqlo-products", {"size": "2XL"}),
        ):
            with self.subTest(department=department, options=options):
                self.assertTrue(size_variant_is_visible(department, options, old_preset))
                self.assertTrue(variants_have_required_size(department, [options]))
                _validate_product_sizes(department, [options])

    def test_size_is_still_required_for_clothing_and_footwear_only(self):
        for department in ("women-muslimah", "uniqlo-products", "batik", "shoe"):
            with self.subTest(department=department):
                self.assertTrue(department_requires_size_selection(department))
                self.assertFalse(variants_have_required_size(department, [{"color": "Red"}]))
                with self.assertRaises(HTTPException) as raised:
                    _validate_product_sizes(department, [{"color": "Red"}])
                self.assertEqual(raised.exception.detail["error"], "size_required_for_department")

        self.assertFalse(department_requires_size_selection("parfum"))
        self.assertTrue(variants_have_required_size("parfum", [{"volume": "50ml"}]))
        _validate_product_sizes("tropical-halal-skincare", [{"format": "serum"}])

    def test_global_size_preset_endpoints_are_removed(self):
        self.assertFalse(
            any("product-size-presets" in route.path for route in admin_router.routes)
        )


if __name__ == "__main__":
    unittest.main()
