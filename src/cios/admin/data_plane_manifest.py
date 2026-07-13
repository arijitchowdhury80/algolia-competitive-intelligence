"""Admin read model for the Hermes-produced Argus data-plane manifest."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cios.admin.types import ArgusDataPlaneManifest

ARTIFACT_NAME = "argus-data-plane-manifest.json"


class ArgusDataPlaneManifestStore:
    """Reads the latest Argus data-plane manifest emitted by the Hermes wrapper."""

    def __init__(
        self,
        *,
        out_dir: Path | None = None,
        work_root: Path | None = None,
        artifact_path: Path | None = None,
    ) -> None:
        self.out_dir = out_dir
        self.work_root = work_root
        self.artifact_path = artifact_path

    def status(self, tenant_slug: str) -> ArgusDataPlaneManifest:
        path = self._resolve_path(tenant_slug)
        if not path.exists():
            return _missing_manifest(tenant_slug, path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return _invalid_manifest(tenant_slug, path, f"could not read manifest: {exc}")
        if not isinstance(payload, dict):
            return _invalid_manifest(tenant_slug, path, "data-plane manifest artifact must be a JSON object")
        if payload.get("tenant_slug") not in {None, tenant_slug}:
            return _invalid_manifest(
                tenant_slug,
                path,
                f"data-plane manifest tenant {payload.get('tenant_slug')} does not match {tenant_slug}",
            )
        return ArgusDataPlaneManifest.model_validate(
            {
                **payload,
                "tenant_slug": tenant_slug,
                "artifact_path": str(path),
                "artifact_found": True,
            }
        )

    def _resolve_path(self, tenant_slug: str) -> Path:
        candidates = self._candidate_paths(tenant_slug)
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    def _candidate_paths(self, tenant_slug: str) -> list[Path]:
        if self.artifact_path is not None:
            return [self.artifact_path]
        if self.out_dir is not None:
            return [self.out_dir / ARTIFACT_NAME]

        candidates: list[Path] = []
        explicit = _env_path("CIOS_DATA_PLANE_MANIFEST_PATH")
        if explicit:
            candidates.append(explicit)
        out_dir = _default_out_dir()
        candidates.append(out_dir / ARTIFACT_NAME)
        work_root = self.work_root or _default_work_root()
        candidates.append(work_root / tenant_slug / ARTIFACT_NAME)

        deduped: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(path)
        return deduped


def _missing_manifest(tenant_slug: str, path: Path) -> ArgusDataPlaneManifest:
    return ArgusDataPlaneManifest(
        tenant_slug=tenant_slug,
        status="not_recorded",
        argus_readiness="unknown",
        next_hermes_action="run_dashboard_refresh",
        source_of_truth={
            "runtime": "Hermes",
            "domain_package": "CI-OS",
            "database": "Postgres evidence ledger",
            "ui_role": "derived readout only",
        },
        artifact_refs={},
        planes={},
        blockers=[],
        safety={
            "ui_must_not_invent_semantics": True,
            "recommendations_require_backend_scorecards": True,
            "empty_or_missing_plane_blocks_promotion": True,
        },
        artifact_path=str(path),
        artifact_found=False,
    )


def _invalid_manifest(tenant_slug: str, path: Path, detail: str) -> ArgusDataPlaneManifest:
    return ArgusDataPlaneManifest(
        tenant_slug=tenant_slug,
        status="artifact_error",
        argus_readiness="unknown",
        next_hermes_action=f"Rebuild the Argus data-plane manifest: {detail}",
        source_of_truth={
            "runtime": "Hermes",
            "domain_package": "CI-OS",
            "database": "Postgres evidence ledger",
            "ui_role": "derived readout only",
        },
        artifact_refs={},
        planes={},
        blockers=[],
        safety={
            "ui_must_not_invent_semantics": True,
            "recommendations_require_backend_scorecards": True,
            "empty_or_missing_plane_blocks_promotion": True,
        },
        artifact_path=str(path),
        artifact_found=False,
    )


def _default_app_dir() -> Path:
    configured = os.environ.get("CIOS_APP_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3]


def _default_out_dir() -> Path:
    configured = os.environ.get("CIOS_OUTPUT_DIR") or os.environ.get("CIOS_DASHBOARD_OUT_DIR")
    if configured:
        return Path(configured)
    return _default_app_dir() / "out"


def _default_work_root() -> Path:
    configured = os.environ.get("CIOS_PRODUCT_MARKET_WORKDIR")
    if configured:
        return Path(configured)
    return Path("/tmp/cios-product-market")


def _env_path(name: str) -> Path | None:
    configured = os.environ.get(name)
    if not configured:
        return None
    return Path(configured).expanduser()
