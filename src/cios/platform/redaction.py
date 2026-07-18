"""Redact sensitive environment-derived values from process diagnostics."""

from __future__ import annotations

import os
from collections.abc import Mapping


_SENSITIVE_KEY_MARKERS = (
    "API_KEY",
    "CREDENTIAL",
    "DATABASE_URL",
    "DSN",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)


def redact_sensitive_text(
    text: str,
    env: Mapping[str, str] | None = None,
    *,
    max_length: int = 500,
) -> str:
    """Replace configured secret values and bound the resulting diagnostic."""

    redacted = str(text or "")
    source = os.environ if env is None else env
    values = {
        str(value)
        for key, value in source.items()
        if value
        and len(str(value)) >= 4
        and any(marker in str(key).upper() for marker in _SENSITIVE_KEY_MARKERS)
    }
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, "[redacted]")
    return redacted[:max_length]
