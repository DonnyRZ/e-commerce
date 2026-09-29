import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/size-tests")
os.environ.setdefault("JWT_SECRET", "isolated-size-test-secret-never-used-for-auth")

from product_sizes import (
    CLOTHING_DEPARTMENTS,
    DEFAULT_CLOTHING_SIZES,
    DEFAULT_FOOTWEAR_SIZES,
    configured_sizes_for_department,
    default_size_preset_data,
    size_variant_matches_config,
    size_variant_is_visible,
    validate_size_values,
)
from db.models import ProductVariant
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from db.models import Category
from routers.catalog import _public_variant_condition
from routers.admin import (
    ProductSizePresetApplyIn,
    _size_preset_plan,
    _unique_size_variant_sku,
    admin_apply_product_size_presets,
)


class FakeScalars:
    def scalars(self):
        return self

    def all(self):
        return []


class ProductSizePresetTests(unittest.IsolatedAsyncioTestCase):
    def test_default_presets_and_supported_departments(self):
        data = default_size_preset_data()
        self.assertEqual(data["clothing"], ["M", "L", "XL", "XXL"])
        self.assertEqual(data["footwear"], ["36", "37", "38", "39", "40"])
        self.assertEqual(CLOTHING_DEPARTMENTS, {"women-muslimah", "uniqlo-products", "batik"})
        self.assertEqual(DEFAULT_CLOTHING_SIZES, data["clothing"])
        self.assertEqual(DEFAULT_FOOTWEAR_SIZES, data["footwear"])
        self.assertIsNone(data["applied_clothing"])
        self.assertTrue(size_variant_is_visible("women-muslimah", {"size": "XS"}, data))
        self.assertTrue(size_variant_is_visible("parfum", {"volume": "50ml"}, data))


    def test_applied_preset_hides_only_legacy_sizes_and_requires_size(self):
        data = default_size_preset_data()
        data["applied_clothing"] = ["M", "L", "XL", "XXL"]
        data["applied_footwear"] = ["36", "37", "38", "39", "40"]
        self.assertTrue(size_variant_is_visible("women-muslimah", {"size": "m"}, data))
        self.assertFalse(size_variant_is_visible("batik", {"size": "S"}, data))
        self.assertFalse(size_variant_is_visible("uniqlo-products", {"color": "Black"}, data))
        self.assertTrue(size_variant_is_visible("shoe", {"size": 40}, data))
        self.assertFalse(size_variant_is_visible("shoe", {"size": 41}, data))
        self.assertTrue(size_variant_is_visible("shoe", {"Size": "40"}, data))
        self.assertTrue(size_variant_is_visible("tropical-halal-skincare", {"volume": "50ml"}, data))
        self.assertEqual(configured_sizes_for_department("women-muslimah", data), data["clothing"])
        self.assertTrue(size_variant_matches_config("shoe", {"size": "36"}, data))
        self.assertFalse(size_variant_matches_config("shoe", {"volume": "50ml"}, data))

    def test_public_variant_filter_keeps_unclassified_departments_and_legacy_size_key(self):
        data = default_size_preset_data()
        data["applied_clothing"] = DEFAULT_CLOTHING_SIZES
        data["applied_footwear"] = DEFAULT_FOOTWEAR_SIZES
        condition = _public_variant_condition(data, Category.department)
        sql = str(condition.compile(dialect=postgresql.dialect())).upper()
        self.assertIn("IS NULL", sql)
        self.assertIn("NOT IN", sql)
        self.assertIn("COALESCE", sql)


    def test_preset_validation_rejects_duplicates_and_empty_values(self):
        self.assertEqual(validate_size_values([" M ", "L"]), ["M", "L"])
        for invalid in ([], ["M", "m"], [" "], ["x" * 33]):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "invalid_size_preset"):
                    validate_size_values(invalid)


    def test_mass_plan_fills_each_color_size_and_preserves_source_metadata(self):
        product = SimpleNamespace(id="product123456", slug="shirt", base_price=125000, status="draft")
        source = SimpleNamespace(
            product_id=product.id,
            sku="SHIRT-BLACK-S",
            option_values={"color": "Black", "size": "S"},
            stock_quantity=7,
            price_override=100000,
            sale_price_override=None,
            media_id="media123456",
            image_url="/media/black.jpg",
            is_active=True,
            id="variant123456",
        )
        data = default_size_preset_data()
        plan, first_digest = _size_preset_plan([(product, "women-muslimah")], [source], data)
        self.assertEqual(len(plan), 1)
        self.assertEqual(len(plan[0]["missing"]), 4)
        self.assertTrue(all(item["option_values"]["color"] == "Black" for item in plan[0]["missing"]))
        self.assertTrue(all(item["is_active"] for item in plan[0]["missing"]))
        self.assertEqual(
            {item["option_values"]["size"] for item in plan[0]["missing"]},
            {"M", "L", "XL", "XXL"},
        )
        self.assertTrue(all(item["media_id"] == source.media_id for item in plan[0]["missing"]))
        self.assertEqual(source.sku, "SHIRT-BLACK-S")
        self.assertEqual(source.stock_quantity, 7)
        self.assertEqual(source.price_override, 100000)
        _, second_digest = _size_preset_plan([(product, "women-muslimah")], [source], data)
        self.assertEqual(first_digest, second_digest)


    def test_mass_plan_is_idempotent_for_existing_size_combinations(self):
        product = SimpleNamespace(id="product123456", slug="shoe", base_price=200000, status="active")
        variants = [
            SimpleNamespace(
                product_id=product.id,
                sku=f"SHOE-{size}",
                option_values={"size": size},
                stock_quantity=0,
                price_override=None,
                sale_price_override=None,
                media_id=None,
                image_url=None,
                is_active=True,
                id=f"variant-{size}",
            )
            for size in DEFAULT_FOOTWEAR_SIZES
        ]
        data = default_size_preset_data()
        plan, _ = _size_preset_plan([(product, "shoe")], variants, data)
        self.assertEqual(plan, [])

    def test_mass_plan_does_not_reactivate_disabled_variant_groups(self):
        product = SimpleNamespace(id="product123456", slug="shirt", base_price=125000, status="active")
        source = SimpleNamespace(
            product_id=product.id,
            sku="SHIRT-BLACK-XS",
            option_values={"color": "Black", "size": "XS"},
            stock_quantity=0,
            price_override=None,
            sale_price_override=None,
            media_id=None,
            image_url=None,
            is_active=False,
            id="variant-disabled",
        )
        plan, _ = _size_preset_plan(
            [(product, "women-muslimah")], [source], default_size_preset_data()
        )
        self.assertTrue(plan)
        self.assertTrue(all(not item["is_active"] for item in plan[0]["missing"]))


    def test_generated_variant_skus_are_unique_and_bounded(self):
        used = {"size-product123-black-m"}
        options = {"color": "Black", "size": "M"}
        first = _unique_size_variant_sku("product123456", options, used)
        second = _unique_size_variant_sku("product123456", options, used)
        self.assertNotEqual(first, second)
        self.assertLessEqual(len(first), 80)
        self.assertLessEqual(len(second), 80)
        self.assertIn(first.casefold(), used)
        self.assertIn(second.casefold(), used)

    async def test_apply_creates_zero_stock_variants_and_commits_preset_together(self):
        product = SimpleNamespace(id="product123456", slug="shirt", base_price=125000, status="draft")
        source = SimpleNamespace(
            product_id=product.id,
            sku="SHIRT-BLACK-XS",
            option_values={"color": "Black", "size": "XS"},
            stock_quantity=7,
            price_override=100000,
            sale_price_override=None,
            media_id="media123456",
            image_url="/media/black.jpg",
            is_active=True,
            id="variant123456",
        )
        data = default_size_preset_data()
        _, digest = _size_preset_plan([(product, "women-muslimah")], [source], data)
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=None),
            execute=AsyncMock(return_value=FakeScalars()),
            add=Mock(),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        with patch("routers.admin.load_size_preset_data", AsyncMock(return_value=data)), \
             patch("routers.admin._size_preset_target_rows", AsyncMock(return_value=([(product, "women-muslimah")], [source]))), \
             patch("routers.admin.audit", AsyncMock()):
            result = await admin_apply_product_size_presets(
                ProductSizePresetApplyIn(preview_digest=digest),
                user=SimpleNamespace(id="admin123"),
                session=session,
            )

        variants = [
            row for (row,), _ in session.add.call_args_list
            if isinstance(row, ProductVariant)
        ]
        self.assertEqual(result["variants_added"], 4)
        self.assertEqual(len(variants), 4)
        self.assertTrue(all(row.stock_quantity == 0 for row in variants))
        self.assertTrue(all(row.price_override is None for row in variants))
        self.assertTrue(all(row.option_values["color"] == "Black" for row in variants))
        self.assertTrue(all(row.is_active for row in variants))
        session.commit.assert_awaited_once()
        self.assertEqual(result["applied_clothing_sizes"], data["clothing"])

    async def test_apply_rejects_stale_preview_without_staging_changes(self):
        product = SimpleNamespace(id="product123456", slug="shirt", base_price=125000, status="draft")
        data = default_size_preset_data()
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=None),
            execute=AsyncMock(return_value=FakeScalars()),
            add=Mock(),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        with patch("routers.admin.load_size_preset_data", AsyncMock(return_value=data)), \
             patch("routers.admin._size_preset_target_rows", AsyncMock(return_value=([(product, "women-muslimah")], []))):
            with self.assertRaises(HTTPException) as raised:
                await admin_apply_product_size_presets(
                    ProductSizePresetApplyIn(preview_digest="0" * 64),
                    user=SimpleNamespace(id="admin123"),
                    session=session,
                )
        self.assertEqual(raised.exception.status_code, 409)
        session.add.assert_not_called()
        session.commit.assert_not_awaited()
