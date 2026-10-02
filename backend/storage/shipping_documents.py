"""Private local storage for admin-only shipping documents."""

import os
from pathlib import Path

from config import SHIPPING_DOCUMENT_ROOT


ROOT = Path(SHIPPING_DOCUMENT_ROOT)


def resolve(key: str) -> Path:
    if not key or Path(key).name != key or key in {".", ".."}:
        raise ValueError("invalid_shipping_document_key")
    return ROOT / key


def save(data: bytes, key: str) -> str:
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    # These documents can contain a recipient's address and phone number.
    # Keep the persistent directory private even if Docker created its bind
    # mount with the usual world-readable directory mode.
    ROOT.chmod(0o700)
    path = resolve(key)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return str(path)


def delete(key: str) -> None:
    try:
        resolve(key).unlink()
    except FileNotFoundError:
        pass
