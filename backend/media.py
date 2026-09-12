"""Small compatibility helpers for the product media JSON field."""


def media_item_url(item) -> str | None:
    """Read both legacy string media and current ``{url, media_id}`` items."""

    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        value = item.get("url")
        return value if isinstance(value, str) else None
    return None
