"""CLICK Shop API signature — MD5 over RAW form strings.

Hard rule (CLICK reference §8/§26): never parse -> normalize -> stringify
before signing. The exact incoming textual values are the signature input.
Comparison uses hmac.compare_digest for safe equality.
"""

import hashlib
import hmac
from typing import Mapping


def compute_signature(fields: Mapping[str, str], secret_key: str, action: str) -> str:
    parts = [
        fields["click_trans_id"],
        fields["service_id"],
        secret_key,
        fields["merchant_trans_id"],
    ]
    if str(action) == "1":
        parts.append(fields.get("merchant_prepare_id", ""))
    parts.extend([fields["amount"], str(action), fields["sign_time"]])
    raw = "".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def verify_signature(fields: Mapping[str, str], secret_key: str, action: str) -> bool:
    expected = compute_signature(fields, secret_key, action)
    incoming = fields.get("sign_string", "")
    return hmac.compare_digest(expected, incoming)
