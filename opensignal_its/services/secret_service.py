"""Secret parsing and constant-time validation helpers."""

from __future__ import annotations

import hashlib
import hmac


def parse_secret_values(raw: str) -> list[str]:
    """Parse comma-separated configured secret values."""
    return [part.strip() for part in raw.split(",") if part.strip()]


def secret_matches(candidate: str, configured: str) -> bool:
    """Match plain or `sha256:<hex>` configured secrets using constant-time comparison."""
    value = candidate.strip()
    if not value or not configured:
        return False

    normalized = configured.strip()
    if normalized.startswith("sha256:"):
        expected_hex = normalized.split(":", 1)[1].strip().lower()
        digest_hex = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest_hex, expected_hex)

    return hmac.compare_digest(value, normalized)


def any_secret_matches(candidate: str, configured_values: list[str]) -> bool:
    for configured in configured_values:
        if secret_matches(candidate, configured):
            return True
    return False
