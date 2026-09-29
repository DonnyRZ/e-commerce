"""Shared size-preset configuration and visibility rules for catalog variants."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MarketplaceSettings


SIZE_PRESETS_SETTING_KEY = "product_size_presets"
DEFAULT_CLOTHING_SIZES = ["M", "L", "XL", "XXL"]
DEFAULT_FOOTWEAR_SIZES = ["36", "37", "38", "39", "40"]
CLOTHING_DEPARTMENTS = frozenset({"women-muslimah", "uniqlo-products", "batik"})
FOOTWEAR_DEPARTMENTS = frozenset({"shoe"})


def validate_size_values(values: list[str]) -> list[str]:
    if not isinstance(values, list) or not 1 <= len(values) <= 24:
        raise ValueError("invalid_size_preset")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError("invalid_size_preset")
        item = value.strip()
        if not item or len(item) > 32 or any(ord(char) < 32 for char in item):
            raise ValueError("invalid_size_preset")
        key = item.casefold()
        if key in seen:
            raise ValueError("invalid_size_preset")
        seen.add(key)
        normalized.append(item)
    return normalized


def default_size_preset_data() -> dict:
    return {
        "clothing": list(DEFAULT_CLOTHING_SIZES),
        "footwear": list(DEFAULT_FOOTWEAR_SIZES),
        # None means no mass-apply has happened yet; until then existing
        # variants stay visible so deploying the feature cannot break sales.
        "applied_clothing": None,
        "applied_footwear": None,
    }


def normalize_size_preset_data(data: Optional[dict]) -> dict:
    result = default_size_preset_data()
    if not isinstance(data, dict):
        return result
    for key in ("clothing", "footwear"):
        try:
            result[key] = validate_size_values(data.get(key, result[key]))
        except ValueError:
            pass
    for key in ("applied_clothing", "applied_footwear"):
        values = data.get(key)
        if values is None:
            result[key] = None
            continue
        try:
            result[key] = validate_size_values(values)
        except ValueError:
            result[key] = None
    return result


async def load_size_preset_data(
    session: AsyncSession, *, shared_lock: bool = False
) -> dict:
    if shared_lock:
        await acquire_size_preset_lock(session, shared=True)
    stmt = select(MarketplaceSettings).where(
        MarketplaceSettings.key == SIZE_PRESETS_SETTING_KEY
    )
    if shared_lock:
        stmt = stmt.with_for_update(read=True, key_share=True)
    setting = await session.scalar(stmt)
    return normalize_size_preset_data(setting.data if setting else None)


async def acquire_size_preset_lock(session: AsyncSession, *, shared: bool) -> None:
    """Serialize size-sensitive writes even before the settings row exists."""

    lock = (
        func.pg_advisory_xact_lock_shared
        if shared
        else func.pg_advisory_xact_lock
    )
    await session.execute(
        select(lock(func.hashtext(f"marketplace-setting:{SIZE_PRESETS_SETTING_KEY}")))
    )


def preset_key_for_department(department: Optional[str]) -> Optional[str]:
    if department in CLOTHING_DEPARTMENTS:
        return "clothing"
    if department in FOOTWEAR_DEPARTMENTS:
        return "footwear"
    return None


def configured_sizes_for_department(
    department: Optional[str], preset_data: dict
) -> Optional[list[str]]:
    key = preset_key_for_department(department)
    if key is None:
        return None
    applied = preset_data.get(f"applied_{key}")
    return applied if applied is not None else preset_data[key]


def size_variant_matches_config(
    department: Optional[str], option_values: Optional[dict], preset_data: dict
) -> bool:
    configured = configured_sizes_for_department(department, preset_data)
    if configured is None:
        return True
    options = option_values if isinstance(option_values, dict) else {}
    size = next(
        (
            value
            for key, value in options.items()
            if str(key).strip().casefold() == "size"
        ),
        None,
    )
    if size is None:
        return False
    allowed = {str(value).strip().casefold() for value in configured}
    return str(size).strip().casefold() in allowed


def size_variant_is_visible(
    department: Optional[str], option_values: Optional[dict], preset_data: dict
) -> bool:
    key = preset_key_for_department(department)
    if key is None:
        return True
    applied = preset_data.get(f"applied_{key}")
    if applied is None:
        return True
    options = option_values if isinstance(option_values, dict) else {}
    size = next(
        (
            value
            for key, value in options.items()
            if str(key).strip().casefold() == "size"
        ),
        None,
    )
    if size is None:
        return False
    allowed = {str(value).strip().casefold() for value in applied}
    return str(size).strip().casefold() in allowed
