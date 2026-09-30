import asyncio

import pytest
from fastapi import HTTPException

from db.models import Product
from routers.seller import _advance_product_revision, _ensure_product_revision


def test_product_revision_increases_monotonically():
    product = Product(revision=1)

    assert _advance_product_revision(product) == 2
    assert _advance_product_revision(product) == 3


def test_missing_expected_revision_is_rejected():
    product = Product(revision=4)

    with pytest.raises(HTTPException) as error:
        asyncio.run(_ensure_product_revision(None, product, None))

    assert error.value.status_code == 428
    assert error.value.detail == {"error": "revision_required"}


def test_matching_revision_is_accepted_without_loading_any_other_data():
    product = Product(revision=7)

    asyncio.run(_ensure_product_revision(None, product, 7))
