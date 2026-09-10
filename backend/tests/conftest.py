"""Test-session bootstrap.

Paid mock orders decrement REAL variant stock; without a reset the dev DB
drifts to zero across repeated suite runs and every cart-add flow fails.
This session fixture restores the known seed stock for the hot variants
used across suites, making the full suite re-runnable. It only touches the
seed SKUs the suites exercise.
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
    "BRS-30ML": 14,      # brightening serum (M7/M8 paid flows)
    "ACBK-BLK-M": 7,     # abaya (M7.1 race/reacquire flows)
    "GSOZH-BGE-M": 12,   # hoodie (M6/M7/M8 cart + paid flows)
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
