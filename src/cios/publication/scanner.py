"""Derive public-safety verdicts from staged artifact bytes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from cios.publication.types import ArtifactRecord, SafetyPolicy, SafetyVerdict


LOCAL_PATH_MARKERS = (
    "/root/",
    "/opt/",
    "/Users/",
    "/tmp/",
    "/private/var/",
    "/app/",
    "C:\\Users\\",
    "file://",
)
MIN_SECRET_LENGTH = 8
CREDENTIAL_FIELD_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "password",
    "private_key",
    "refresh_token",
}


class UnsafeArtifactError(ValueError):
    """A staged artifact contains material that cannot be public."""


def _rules_for_text(text: str, policy: SafetyPolicy) -> set[str]:
    """Return non-sensitive rule identifiers for unsafe text."""
    rules: set[str] = set()
    if any(marker in text for marker in LOCAL_PATH_MARKERS):
        rules.add("local_path")
    for secret in policy.secret_values:
        value = secret.get_secret_value()
        if len(value) >= MIN_SECRET_LENGTH and value in text:
            rules.add("configured_secret")
    return rules


def _contains_credential_field(value: Any) -> bool:
    """Detect non-empty credential values without returning their contents."""
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in CREDENTIAL_FIELD_NAMES and _is_nonempty(item):
                return True
            if _contains_credential_field(item):
                return True
    elif isinstance(value, list):
        return any(_contains_credential_field(item) for item in cast(list[object], value))
    return False


def _is_nonempty(value: Any) -> bool:
    """Treat any populated scalar or container as credential material."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(cast(object, value))
    return value is not None


def scan_generation(
    generation_dir: Path,
    records: list[ArtifactRecord],
    policy: SafetyPolicy,
) -> SafetyVerdict:
    """Scan every staged text artifact and return a derived safety verdict."""
    for record in records:
        path = generation_dir / record.path
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise UnsafeArtifactError(f"unsafe artifact {record.path}: invalid_utf8") from exc
        rules = _rules_for_text(text, policy)
        if record.media_type == "application/json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if _contains_credential_field(payload):
                rules.add("credential_field")
        if rules:
            raise UnsafeArtifactError(f"unsafe artifact {record.path}: {','.join(sorted(rules))}")
    return SafetyVerdict(
        artifact_paths_redacted=True,
        secret_values_included=False,
        public_safe=True,
    )
