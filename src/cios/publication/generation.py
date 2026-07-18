"""Build immutable CI-OS publication generations."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path

from cios.publication.types import (
    ArtifactRecord,
    PublicationManifest,
    PublicationRequest,
    SafetyPolicy,
    SafetyVerdict,
)
from cios.publication.scanner import UnsafeArtifactError, scan_generation


logger = logging.getLogger(__name__)
MANIFEST_NAME = "publication-manifest.json"
PUBLIC_STATUS_PATH = "data/argus-latest-run-status.json"


class PublicationValidationError(ValueError):
    """A generation failed a publication integrity check."""


def _copy_artifact(source: Path, target: Path) -> None:
    """Copy one declared regular file without following a symlink boundary."""
    if source.is_symlink() or not source.is_file():
        raise PublicationValidationError(f"artifact source is not a regular file: {source.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target, follow_symlinks=False)
    except OSError:
        logger.exception("copy_artifact | failed | source=%s | target=%s", source, target)
        raise


def _record(path: Path, public_path: str, media_type: str) -> ArtifactRecord:
    """Create the content record for one copied artifact."""
    content = path.read_bytes()
    if not content:
        raise PublicationValidationError(f"artifact is empty: {public_path}")
    return ArtifactRecord(
        path=public_path,
        media_type=media_type,
        bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _manifest(
    request: PublicationRequest,
    records: list[ArtifactRecord],
    safety: SafetyVerdict,
) -> PublicationManifest:
    """Build a deterministic manifest from copied artifact records."""
    return PublicationManifest(
        run_id=request.identity.run_id,
        tenant_slug=request.identity.tenant_slug,
        kind=request.kind,
        generated_at=request.generated_at,
        files=tuple(sorted(records, key=lambda item: item.path)),
        safety=safety,
    )


def _write_derived_status_safety(
    generation_dir: Path,
    records: list[ArtifactRecord],
    safety: SafetyVerdict,
) -> list[ArtifactRecord]:
    """Replace caller-provided status safety with the byte-derived verdict."""
    status_record = next((record for record in records if record.path == PUBLIC_STATUS_PATH), None)
    if status_record is None:
        return records
    status_path = generation_dir / PUBLIC_STATUS_PATH
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return records
    if not isinstance(payload, dict):
        return records
    payload["safety"] = safety.model_dump(mode="json")
    status_path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    return [
        _record(generation_dir / record.path, record.path, record.media_type)
        for record in records
    ]


def build_generation(
    request: PublicationRequest,
    generation_dir: Path,
    safety_policy: SafetyPolicy | None = None,
) -> PublicationManifest:
    """Copy declared artifacts and write their canonical generation manifest."""
    policy = safety_policy or SafetyPolicy()
    if generation_dir.exists():
        raise PublicationValidationError(f"generation already exists: {request.identity.run_id}")
    generation_dir.mkdir(parents=True)
    records: list[ArtifactRecord] = []
    try:
        for artifact in request.artifacts:
            target = generation_dir / artifact.public_path
            _copy_artifact(artifact.source_path, target)
            records.append(_record(target, artifact.public_path, artifact.media_type))
        try:
            safety = scan_generation(generation_dir, records, policy)
        except UnsafeArtifactError as exc:
            raise PublicationValidationError(str(exc)) from exc
        records = _write_derived_status_safety(generation_dir, records, safety)
        try:
            final_safety = scan_generation(generation_dir, records, policy)
        except UnsafeArtifactError as exc:
            raise PublicationValidationError(str(exc)) from exc
        if final_safety != safety:
            raise PublicationValidationError("status safety finalization changed scanner verdict")
        manifest = _manifest(request, records, safety)
        payload = f"{manifest.model_dump_json(indent=2)}\n"
        (generation_dir / MANIFEST_NAME).write_text(payload, encoding="utf-8")
        return manifest
    except Exception as exc:
        if isinstance(exc, PublicationValidationError):
            logger.warning("build_generation | validation_failed | run_id=%s", request.identity.run_id)
        else:
            logger.exception(
                "build_generation | failed | run_id=%s | generation_dir=%s",
                request.identity.run_id,
                generation_dir,
            )
        shutil.rmtree(generation_dir, ignore_errors=True)
        raise
