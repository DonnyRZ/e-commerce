"""Test-session bootstrap.

Some integration tests mutate real seed inventory; without a reset the dev DB
drifts to zero across repeated suite runs and cart-add flows fail. This session
fixture restores the known seed stock for the variants used across suites.
"""

import asyncio
import os

import asyncpg

import pytest

DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql://marketplace:marketplace@localhost:55433/marketplace",
    ),
).replace("postgresql+asyncpg://", "postgresql://", 1)

SEED_STOCK = {
    "BRS-30ML": 14,      # brightening serum cart flows
    "ACBK-BLK-M": 7,     # abaya cart flows
    "GSOZH-BGE-M": 12,   # hoodie cart flows
    "GSOZH-GRY-XS": 2,   # hoodie low-stock variant (stock-cap tests)
    "GSOZH-NVY-XXL": 12,
    "GSOZH-BLK-XXL": 0,  # OOS fixture variant
}


@pytest.fixture(scope="session", autouse=True)
def reset_seed_stock():
    async def _reset():
        connection = await asyncpg.connect(DB_URL)
        try:
            for sku, quantity in SEED_STOCK.items():
                await connection.execute(
                    "UPDATE product_variants SET stock_quantity = $1 WHERE sku = $2",
                    quantity,
                    sku,
                )
        finally:
            await connection.close()

    asyncio.run(_reset())
    yield
