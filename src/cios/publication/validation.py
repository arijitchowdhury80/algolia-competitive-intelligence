"""Independent validation for completed CI-OS public generations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from cios.publication.generation import MANIFEST_NAME, PublicationValidationError
from cios.publication.scanner import UnsafeArtifactError, scan_generation
from cios.publication.types import (
    GenerationValidationPolicy,
    PublicationKind,
    PublicationManifest,
    RunIdentity,
)


DECISION_REQUIRED_PATHS = {
    "index.html",
    "brief.html",
    "data/semantic-dashboard.json",
    "data/argus-data-plane-manifest.json",
    "data/argus-latest-run-status.json",
    "verdicts/hermes-package-contract.json",
}
DIAGNOSTIC_REQUIRED_PATHS = {"data/argus-latest-run-status.json"}


def _load_manifest(generation_dir: Path) -> PublicationManifest:
    """Load the generation manifest without following a manifest symlink."""
    path = generation_dir / MANIFEST_NAME
    if path.is_symlink() or not path.is_file():
        raise PublicationValidationError("missing regular publication manifest")
    try:
        return PublicationManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise PublicationValidationError("invalid publication manifest") from exc


def _artifact_paths(generation_dir: Path) -> set[str]:
    """Enumerate regular files and reject any symlink in the final tree."""
    paths: set[str] = set()
    for path in generation_dir.rglob("*"):
        if path.is_symlink():
            raise PublicationValidationError("generation contains symlink")
        if path.is_file() and path.name != MANIFEST_NAME:
            paths.add(path.relative_to(generation_dir).as_posix())
    return paths


def _validate_required_paths(manifest: PublicationManifest, paths: set[str]) -> None:
    """Require the complete artifact class for the generation kind."""
    required = DECISION_REQUIRED_PATHS if manifest.kind is PublicationKind.DECISION else DIAGNOSTIC_REQUIRED_PATHS
    missing = required - paths
    if manifest.kind is PublicationKind.DECISION and not any(path.startswith("briefs/") for path in paths):
        missing.add("briefs/<competitor>.html")
    if missing:
        raise PublicationValidationError(f"missing required artifact: {sorted(missing)[0]}")


def _validate_hashes(generation_dir: Path, manifest: PublicationManifest) -> None:
    """Recompute every declared size and digest from final bytes."""
    for record in manifest.files:
        path = generation_dir / record.path
        content = path.read_bytes()
        if len(content) != record.bytes or hashlib.sha256(content).hexdigest() != record.sha256:
            raise PublicationValidationError(f"artifact hash mismatch: {record.path}")


def _parse_json(path: Path) -> dict[str, Any]:
    """Read one required structured public artifact."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationValidationError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(payload, dict):
        raise PublicationValidationError(f"invalid JSON artifact: {path.name}")
    return cast(dict[str, Any], payload)


def _dict_value(value: Any) -> dict[str, Any]:
    """Narrow an untrusted JSON value to a string-keyed object."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _run_ids(generation_dir: Path, kind: PublicationKind) -> list[object]:
    """Read the current-run identity fields from authoritative JSON files."""
    status = _parse_json(generation_dir / "data/argus-latest-run-status.json")
    if kind is PublicationKind.DIAGNOSTIC:
        return [status.get("run_id")]
    manifest = _parse_json(generation_dir / "data/argus-data-plane-manifest.json")
    dashboard = _parse_json(generation_dir / "data/semantic-dashboard.json")
    return [
        status.get("run_id"),
        manifest.get("run_id"),
        _dict_value(dashboard.get("run_health")).get("run_id"),
        _dict_value(dashboard.get("product_market_run")).get("run_id"),
    ]


def _validate_freshness(manifest: PublicationManifest, policy: GenerationValidationPolicy) -> None:
    """Reject stale or implausibly future generation timestamps."""
    age = (policy.now - manifest.generated_at).total_seconds()
    if age > policy.max_age_seconds:
        raise PublicationValidationError("stale generation")
    if age < -policy.max_future_skew_seconds:
        raise PublicationValidationError("generation timestamp is in the future")


def _validate_structured_freshness(
    generation_dir: Path,
    kind: PublicationKind,
    policy: GenerationValidationPolicy,
) -> None:
    """Require every current-run JSON artifact to carry a fresh aware timestamp."""
    paths = ["data/argus-latest-run-status.json"]
    if kind is PublicationKind.DECISION:
        paths.extend(
            [
                "data/argus-data-plane-manifest.json",
                "data/semantic-dashboard.json",
            ]
        )
    for relative_path in paths:
        payload = _parse_json(generation_dir / relative_path)
        raw_generated_at = payload.get("generated_at")
        try:
            generated_at = datetime.fromisoformat(str(raw_generated_at).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise PublicationValidationError(
                f"invalid structured artifact timestamp: {relative_path}"
            ) from exc
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise PublicationValidationError(
                f"invalid structured artifact timestamp: {relative_path}"
            )
        age = (policy.now - generated_at).total_seconds()
        if age > policy.max_age_seconds:
            raise PublicationValidationError(f"stale structured artifact: {relative_path}")
        if age < -policy.max_future_skew_seconds:
            raise PublicationValidationError(
                f"structured artifact timestamp is in the future: {relative_path}"
            )


def _validate_package_verdict(
    generation_dir: Path,
    identity: RunIdentity,
    policy: GenerationValidationPolicy,
) -> None:
    """Require a fresh, passing, run-bound package contract verdict."""
    relative_path = "verdicts/hermes-package-contract.json"
    payload = _parse_json(generation_dir / relative_path)
    checks = payload.get("checks")
    typed_checks = cast(dict[object, object], checks) if isinstance(checks, dict) else {}
    valid = (
        payload.get("schema_version") == 1
        and payload.get("gate") == "hermes_package_contract"
        and payload.get("run_id") == identity.run_id
        and payload.get("status") == "pass"
        and payload.get("exit_code") == 0
        and bool(typed_checks)
        and all(value is True for value in typed_checks.values())
    )
    if not valid:
        raise PublicationValidationError("invalid structured verdict: hermes_package_contract")
    generated_at = _parse_aware_timestamp(payload.get("generated_at"), relative_path)
    age = (policy.now - generated_at).total_seconds()
    if age > policy.max_age_seconds or age < -policy.max_future_skew_seconds:
        raise PublicationValidationError("invalid structured verdict: hermes_package_contract")


def _parse_aware_timestamp(value: Any, relative_path: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PublicationValidationError(
            f"invalid structured artifact timestamp: {relative_path}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PublicationValidationError(f"invalid structured artifact timestamp: {relative_path}")
    return parsed


def validate_generation(
    generation_dir: Path,
    identity: RunIdentity,
    policy: GenerationValidationPolicy,
) -> PublicationManifest:
    """Independently prove final tree, identity, freshness, hashes, and safety."""
    manifest = _load_manifest(generation_dir)
    if manifest.run_id != identity.run_id or manifest.tenant_slug != identity.tenant_slug:
        raise PublicationValidationError("manifest identity mismatch")
    _validate_freshness(manifest, policy)
    actual_paths = _artifact_paths(generation_dir)
    expected_paths = {record.path for record in manifest.files}
    if actual_paths - expected_paths:
        raise PublicationValidationError(f"unexpected artifact: {sorted(actual_paths - expected_paths)[0]}")
    if expected_paths - actual_paths:
        raise PublicationValidationError(f"missing artifact: {sorted(expected_paths - actual_paths)[0]}")
    _validate_required_paths(manifest, actual_paths)
    _validate_hashes(generation_dir, manifest)
    _validate_structured_freshness(generation_dir, manifest.kind, policy)
    if manifest.kind is PublicationKind.DECISION:
        _validate_package_verdict(generation_dir, identity, policy)
    if any(run_id != identity.run_id for run_id in _run_ids(generation_dir, manifest.kind)):
        raise PublicationValidationError("run identity mismatch")
    try:
        safety = scan_generation(generation_dir, list(manifest.files), policy.safety)
    except UnsafeArtifactError as exc:
        raise PublicationValidationError(str(exc)) from exc
    if safety != manifest.safety:
        raise PublicationValidationError("manifest safety mismatch")
    return manifest
