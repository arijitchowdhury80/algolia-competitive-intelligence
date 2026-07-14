"""Immutable generation storage and atomic CI-OS publication pointers."""

from __future__ import annotations

import hashlib
import fcntl
import logging
import os
import shutil
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from cios.publication.generation import PublicationValidationError, build_generation
from cios.publication.types import (
    PublicationKind,
    PublicationRequest,
    PublicationResult,
    PublicRunStatus,
    GenerationValidationPolicy,
)
from cios.publication.validation import validate_generation


logger = logging.getLogger(__name__)
STATUS_PATH = Path("data/argus-latest-run-status.json")
ROUTER_LINKS = {
    Path("index.html"): Path("../current/index.html"),
    Path("brief.html"): Path("../current/brief.html"),
    Path("briefs"): Path("../current/briefs"),
    Path("data/semantic-dashboard.json"): Path("../../current/data/semantic-dashboard.json"),
    Path("data/argus-data-plane-manifest.json"): Path("../../current/data/argus-data-plane-manifest.json"),
    Path("data/argus-demand-plan-template.csv"): Path("../../current/data/argus-demand-plan-template.csv"),
    Path("data/argus-demand-work-order-guide.json"): Path(
        "../../current/data/argus-demand-work-order-guide.json"
    ),
    Path("data/argus-latest-run-status.json"): Path("../../latest-status.json"),
    Path("publication-manifest.json"): Path("../current/publication-manifest.json"),
    Path("v2/index.html"): Path("../../current/index.html"),
    Path("v2/brief.html"): Path("../../current/brief.html"),
    Path("v2/briefs"): Path("../../current/briefs"),
    Path("v2/data/semantic-dashboard.json"): Path("../../../current/data/semantic-dashboard.json"),
    Path("v2/data/argus-data-plane-manifest.json"): Path(
        "../../../current/data/argus-data-plane-manifest.json"
    ),
    Path("v2/data/argus-demand-plan-template.csv"): Path(
        "../../../current/data/argus-demand-plan-template.csv"
    ),
    Path("v2/data/argus-demand-work-order-guide.json"): Path(
        "../../../current/data/argus-demand-work-order-guide.json"
    ),
    Path("v2/data/argus-latest-run-status.json"): Path("../../../latest-status.json"),
    Path("v2/publication-manifest.json"): Path("../../current/publication-manifest.json"),
}


class FileOps(Protocol):
    """Filesystem operations that define the atomic commit boundary."""

    def replace(self, source: Path, target: Path) -> None:
        """Atomically replace target with source."""
        ...


class LocalFileOps:
    """Production implementation of atomic filesystem replacement."""

    def replace(self, source: Path, target: Path) -> None:
        """Use the operating system's same-filesystem atomic replace."""
        os.replace(source, target)


class PublicationStore:
    """Install and promote validated CI-OS generations."""

    def __init__(
        self,
        root: Path,
        validation_policy: GenerationValidationPolicy | None = None,
        file_ops: FileOps | None = None,
    ) -> None:
        """Create a store handle without mutating the filesystem."""
        self.root = root
        self.validation_policy = validation_policy
        self.file_ops = file_ops or LocalFileOps()

    def _policy(self) -> GenerationValidationPolicy:
        """Return the injected policy or a fresh production-time policy."""
        return self.validation_policy or GenerationValidationPolicy(now=datetime.now(timezone.utc))

    def _ensure_layout(self) -> None:
        """Create immutable stores and the stable compatibility router."""
        for relative in (
            "releases",
            "diagnostics",
            ".staging",
            "served",
            "served/data",
            "served/v2",
            "served/v2/data",
        ):
            path = self.root / relative
            if path.is_symlink():
                raise PublicationValidationError(f"store path must be a real directory: {relative}")
            path.mkdir(parents=True, exist_ok=True)
            if not path.is_dir():
                raise PublicationValidationError(f"store path must be a real directory: {relative}")
        for route, target in ROUTER_LINKS.items():
            link = self.root / "served" / route
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.exists() or link.is_symlink():
                if not link.is_symlink() or link.readlink() != target:
                    raise PublicationValidationError(f"router link mismatch: {route}")
                continue
            link.symlink_to(target)

    @contextmanager
    def _exclusive_lock(self) -> Generator[None, None, None]:
        """Serialize publishers and reject a redirected publication root."""
        if self.root.is_symlink():
            raise PublicationValidationError("publication root must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise PublicationValidationError("publication root must be a directory")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.root / ".publish.lock", flags, 0o600)
        except OSError as exc:
            raise PublicationValidationError("invalid publication lock") from exc
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _status(self, stage: Path, request: PublicationRequest) -> PublicRunStatus:
        """Validate status identity, safety, and decision semantics."""
        try:
            status = PublicRunStatus.model_validate_json((stage / STATUS_PATH).read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise PublicationValidationError("invalid public run status") from exc
        if status.run_id != request.identity.run_id or status.tenant_slug != request.identity.tenant_slug:
            raise PublicationValidationError("public status identity mismatch")
        expected = "published" if request.kind is PublicationKind.DECISION else "blocked"
        if status.publish_status != expected:
            raise PublicationValidationError("public status kind mismatch")
        return status

    def _replace_pointer(self, name: str, target: Path) -> None:
        """Atomically replace one relative generation symlink."""
        temporary = self.root / f".{name}.tmp.{os.getpid()}"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target, target_is_directory=True)
        self.file_ops.replace(temporary, self.root / name)

    def _replace_status(self, source: Path) -> None:
        """Atomically replace the single status inode shared by all routes."""
        temporary = self.root / f".latest-status.tmp.{os.getpid()}"
        content = source.read_bytes()
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self.file_ops.replace(temporary, self.root / "latest-status.json")
        finally:
            temporary.unlink(missing_ok=True)

    def _pointer_target(self, name: str) -> Path | None:
        """Read the current relative pointer target if one exists."""
        pointer = self.root / name
        return pointer.readlink() if pointer.is_symlink() else None

    def _restore_pointer(self, name: str, prior_target: Path | None) -> None:
        """Restore or remove a pointer after a failed status commit."""
        pointer = self.root / name
        if prior_target is None:
            pointer.unlink(missing_ok=True)
            return
        self._replace_pointer(name, prior_target)

    def publish(
        self,
        request: PublicationRequest,
    ) -> PublicationResult:
        """Install one generation, promote its pointer, and write status last."""
        with self._exclusive_lock():
            return self._publish_locked(request)

    def _publish_locked(self, request: PublicationRequest) -> PublicationResult:
        """Publish while holding the store-wide process lock."""
        self._ensure_layout()
        stage = self.root / ".staging" / request.identity.run_id
        bucket = "releases" if request.kind is PublicationKind.DECISION else "diagnostics"
        final = self.root / bucket / request.identity.run_id
        pointer = "current" if request.kind is PublicationKind.DECISION else "latest-diagnostics"
        prior_target = self._pointer_target(pointer)
        installed = False
        promoted = False
        if final.exists():
            raise PublicationValidationError(f"generation already exists: {request.identity.run_id}")
        try:
            policy = self._policy()
            build_generation(request, stage, policy.safety)
            manifest = validate_generation(stage, request.identity, policy)
            status = self._status(stage, request)
            if status.safety != manifest.safety:
                raise PublicationValidationError("public status safety mismatch")
            manifest_bytes = (stage / "publication-manifest.json").read_bytes()
            self.file_ops.replace(stage, final)
            installed = True
            self._replace_pointer(pointer, Path(bucket) / request.identity.run_id)
            promoted = True
            self._replace_status(final / STATUS_PATH)
            return PublicationResult(
                run_id=request.identity.run_id,
                status=status.publish_status,
                generation_path=final,
                manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            )
        except Exception as exc:
            if isinstance(exc, PublicationValidationError):
                logger.warning(
                    "publish | validation_failed | run_id=%s | kind=%s",
                    request.identity.run_id,
                    request.kind,
                )
            else:
                logger.exception("publish | failed | run_id=%s | kind=%s", request.identity.run_id, request.kind)
            shutil.rmtree(stage, ignore_errors=True)
            if promoted:
                try:
                    self._restore_pointer(pointer, prior_target)
                except OSError as rollback_error:
                    logger.exception(
                        "publish | rollback_failed | run_id=%s | pointer=%s",
                        request.identity.run_id,
                        pointer,
                    )
                    raise PublicationValidationError("publication pointer rollback failed") from rollback_error
            if installed:
                shutil.rmtree(final, ignore_errors=True)
            raise
