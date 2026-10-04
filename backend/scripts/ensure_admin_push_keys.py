"""Generate a persistent VAPID key once; never print the private key."""

import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def ensure_key(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        data = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise RuntimeError("Existing VAPID key must be an EC P-256 private key")
    path.chmod(0o600)
    print("Persistent admin push key is ready.")


if __name__ == "__main__":
    ensure_key(
        Path(
            os.environ.get("VAPID_PRIVATE_KEY_FILE", "/app/push-keys/vapid-private.pem")
        )
    )
