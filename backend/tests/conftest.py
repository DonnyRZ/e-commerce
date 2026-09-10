"""Test-session bootstrap.

Paid mock orders decrement REAL variant stock; without a reset the dev DB
drifts to zero across repeated suite runs and every cart-add flow fails.
This session fixture restores the known seed stock for the hot variants
used across suites, making the full suite re-runnable. It only touches the
seed SKUs the suites exercise.
"""

import subprocess

import pytest

DB_URL = "postgresql://muslimah:muslimah_dev_pass@localhost:5432/muslimah_cantik"

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
    values = ",".join(f"('{sku}', {qty})" for sku, qty in SEED_STOCK.items())
    subprocess.run(
        [
            "psql", DB_URL, "-c",
            "UPDATE product_variants v SET stock_quantity = s.qty "
            f"FROM (VALUES {values}) AS s(sku, qty) WHERE v.sku = s.sku",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    yield
